"""
小说世界分块图谱构建器
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from ..models.task import TaskManager, TaskStatus
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .neo4j_graph_store import Neo4jGraphStore
from .text_processor import TextProcessor


BUILD_EXTRACTION_SYSTEM_PROMPT = """你是小说世界增量知识图谱抽取器。

请从文本块中抽取实体、关系和演进线索。
只输出 JSON，不要解释。

输出格式：
{
  "entities": [
    {
      "name": "实体名称",
      "entity_type": "Person|Faction|Location|Creature|Artifact|PowerSystem|Event|Organization|Family|Unknown",
      "description": "简要描述",
      "aliases": ["别名1", "别名2"],
      "attributes": {
        "appearance": "外貌相关事实",
        "identity": "身份、职业、阵营",
        "stage": "当前阶段或形态"
      }
    }
  ],
  "relationships": [
    {
      "source": "源实体名称",
      "relation_type": "KNOWS|ALLIED_WITH|OPPOSES|LOCATED_IN|BELONGS_TO|HAS_POWER|OWNS|MENTORS|FAMILY_OF|TARGETS|INTERACTS_WITH",
      "target": "目标实体名称",
      "description": "关系说明"
    }
  ],
  "observations": ["关键事件", "身份揭示", "世界规则变化"]
}
"""


MERGE_DECISION_SYSTEM_PROMPT = """你是小说人物归并判断器。

你会判断一个新抽取实体是否与候选实体为同一实体、别名、同一实体的阶段演进，或者是新实体。
只输出 JSON。

输出格式：
{
  "decision": "existing|new",
  "entity_id": "候选实体ID或空字符串",
  "alias": "若是别名则给出别名，否则空字符串",
  "evolution_note": "若是同一实体的阶段演进则说明",
  "reason": "简要原因"
}
"""

CORE_ENTITY_TYPES = {"Character", "Organization", "Faction", "Location", "Family", "PowerSystem", "Artifact"}
MIN_ACTIVE_IMPORTANCE = 2.4
DORMANT_AFTER_CHUNKS = 48
DORMANT_MAX_IMPORTANCE = 3.4


@dataclass
class CanonicalEntity:
    entity_id: str
    name: str
    entity_type: str
    description: str
    aliases: set[str]
    attributes: Dict[str, Any]
    first_seen_chunk: int
    last_seen_chunk: int
    appearance_count: int = 1
    connected_core_count: int = 0
    importance_score: float = 0.0
    state: str = "candidate"
    archive_reason: str = ""

    def to_row(self) -> Dict[str, Any]:
        status_summary = self.attributes.get("stage") or self.attributes.get("identity") or self.description
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "entity_type": self.entity_type,
            "description": self.description,
            "aliases": sorted(self.aliases),
            "attributes": self.attributes,
            "status_summary": status_summary,
            "first_seen_chunk": self.first_seen_chunk,
            "last_seen_chunk": self.last_seen_chunk,
            "appearance_count": self.appearance_count,
            "connected_core_count": self.connected_core_count,
            "importance_score": self.importance_score,
            "state": self.state,
            "archive_reason": self.archive_reason,
        }


class NovelGraphBuilder:
    def __init__(
        self,
        graph_store: Optional[Neo4jGraphStore] = None,
        llm_client: Optional[LLMClient] = None,
    ):
        self.graph_store = graph_store or Neo4jGraphStore()
        self.llm_client = llm_client or LLMClient()
        self.logger = get_logger("mirofish.graph_builder")
        self.canonical_entities: Dict[str, CanonicalEntity] = {}
        self.entity_name_index: Dict[str, str] = {}
        self.relation_index: Dict[tuple[str, str, str], Dict[str, Any]] = {}
        self.archived_snapshots: Dict[str, Dict[str, Any]] = {}

    def build_graph(
        self,
        *,
        graph_id: Optional[str],
        graph_name: str,
        text: str,
        simulation_requirement: str,
        ontology: Optional[Dict[str, Any]],
        chunk_size: int,
        chunk_overlap: int,
        task_manager: TaskManager,
        task_id: str,
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        graph_id = graph_id or self.graph_store.create_graph(
            name=graph_name,
            description="MiroFish Novel World Graph",
        )
        chunks = TextProcessor.split_text(text, chunk_size=chunk_size, overlap=chunk_overlap)
        total_chunks = max(len(chunks), 1)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        self.logger.info("开始分块构图: 总块数=%s, chunk_size=%s, overlap=%s", total_chunks, chunk_size, chunk_overlap)

        for index, chunk in enumerate(chunks):
            self.logger.info("构图子任务 %s/%s", index + 1, total_chunks)
            task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=min(95, 5 + int((index / total_chunks) * 85)),
                message=f"处理文本块 {index + 1}/{total_chunks}",
                progress_detail={
                    "provider": "neo4j",
                    "current_chunk": index + 1,
                    "total_chunks": total_chunks,
                    "graph_id": graph_id,
                },
            )
            extracted = self._extract_chunk(
                chunk=chunk,
                chunk_index=index,
                simulation_requirement=simulation_requirement,
                ontology=ontology,
            )
            chunk_entities = self._merge_entities(extracted.get("entities", []), index)
            chunk_relationships = self._merge_relationships(extracted.get("relationships", []), chunk_entities, chunk, index)
            synced_entities, state_changes, touched_ids = self._evaluate_entity_lifecycle(chunk_entities, chunk_relationships, index)
            syncable_relationships = self._collect_syncable_relationships(touched_ids)
            if synced_entities:
                self.graph_store.upsert_entities(graph_id, [entity.to_row() for entity in synced_entities], index)
            if syncable_relationships:
                self.graph_store.upsert_relationships(graph_id, syncable_relationships, index)
            if output_dir:
                self._write_chunk_result(
                    output_dir=output_dir,
                    chunk_index=index,
                    chunk_text=chunk,
                    extracted=extracted,
                    chunk_entities=chunk_entities,
                    chunk_relationships=syncable_relationships,
                    graph_id=graph_id,
                    state_changes=state_changes,
                )

        graph_data = self.graph_store.get_graph_data(graph_id)
        if output_dir:
            self._write_archive_result(output_dir)
            self._write_summary_result(output_dir, graph_data, total_chunks, graph_id)
        task_manager.update_task(
            task_id,
            progress=100,
            message="图谱构建完成",
            progress_detail={
                "provider": "neo4j",
                "current_chunk": total_chunks,
                "total_chunks": total_chunks,
                "graph_id": graph_id,
            },
        )
        return {
            "graph_id": graph_id,
            "node_count": graph_data["node_count"],
            "edge_count": graph_data["edge_count"],
            "chunk_count": total_chunks,
        }

    def _write_chunk_result(
        self,
        *,
        output_dir: str,
        chunk_index: int,
        chunk_text: str,
        extracted: Dict[str, Any],
        chunk_entities: List[CanonicalEntity],
        chunk_relationships: List[Dict[str, Any]],
        graph_id: str,
        state_changes: List[Dict[str, Any]],
    ) -> None:
        payload = {
            "graph_id": graph_id,
            "chunk_index": chunk_index + 1,
            "chunk_length": len(chunk_text),
            "raw_entity_count": len(extracted.get("entities", [])),
            "raw_relationship_count": len(extracted.get("relationships", [])),
            "merged_entity_count": len(chunk_entities),
            "merged_relationship_count": len(chunk_relationships),
            "entity_type_top5": self._top_counts(
                [entity.get("entity_type", "Unknown") for entity in extracted.get("entities", [])]
            ),
            "relation_type_top5": self._top_counts(
                [relation.get("relation_type", "INTERACTS_WITH") for relation in extracted.get("relationships", [])]
            ),
            "state_changes": state_changes,
            "canonical_entities": [entity.to_row() for entity in chunk_entities],
            "relationships": chunk_relationships,
            "preview": chunk_text[:300],
            "raw_result": extracted,
        }
        path = os.path.join(output_dir, f"chunk_{chunk_index + 1:03d}.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    def _write_summary_result(
        self,
        output_dir: str,
        graph_data: Dict[str, Any],
        total_chunks: int,
        graph_id: str,
    ) -> None:
        payload = {
            "graph_id": graph_id,
            "chunk_count": total_chunks,
            "node_count": graph_data.get("node_count", 0),
            "edge_count": graph_data.get("edge_count", 0),
            "candidate_count": sum(1 for entity in self.canonical_entities.values() if entity.state == "candidate"),
            "dormant_count": sum(1 for entity in self.canonical_entities.values() if entity.state == "dormant"),
            "active_count": sum(1 for entity in self.canonical_entities.values() if entity.state == "active"),
            "entity_type_top10": self._top_counts(
                [node.get("labels", [None, "Entity"])[-1] for node in graph_data.get("nodes", [])]
            ),
        }
        path = os.path.join(output_dir, "summary.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    def _write_archive_result(self, output_dir: str) -> None:
        payload = {
            "archived_count": len(self.archived_snapshots),
            "entities": list(self.archived_snapshots.values()),
        }
        path = os.path.join(output_dir, "archive_entities.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    def _top_counts(self, values: List[str]) -> List[Dict[str, Any]]:
        counter: Dict[str, int] = {}
        for value in values:
            if not value:
                continue
            counter[value] = counter.get(value, 0) + 1
        sorted_items = sorted(counter.items(), key=lambda item: item[1], reverse=True)
        return [{"name": name, "count": count} for name, count in sorted_items[:5]]

    def _extract_chunk(
        self,
        *,
        chunk: str,
        chunk_index: int,
        simulation_requirement: str,
        ontology: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        prompt = {
            "simulation_requirement": simulation_requirement,
            "chunk_index": chunk_index + 1,
            "ontology": ontology or {},
            "chunk": chunk,
        }
        return self.llm_client.chat_json(
            messages=[
                {"role": "system", "content": BUILD_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            temperature=0.1,
            max_tokens=2048,
        )

    def _merge_entities(self, entities: List[Dict[str, Any]], chunk_index: int) -> List[CanonicalEntity]:
        merged_entities: Dict[str, CanonicalEntity] = {}
        for entity in entities:
            name = (entity.get("name") or "").strip()
            if not name:
                continue

            entity_type = entity.get("entity_type") or "Unknown"
            description = (entity.get("description") or "").strip()
            aliases = {alias.strip() for alias in entity.get("aliases", []) if alias and alias.strip()}
            aliases.add(name)
            attributes = entity.get("attributes") or {}

            existing_id = self._resolve_existing_entity_id(
                name=name,
                entity_type=entity_type,
                description=description,
                aliases=aliases,
                attributes=attributes,
            )

            if existing_id:
                canonical = self.canonical_entities[existing_id]
                canonical.aliases.update(aliases)
                canonical.last_seen_chunk = chunk_index
                canonical.appearance_count += 1
                if description and len(description) > len(canonical.description):
                    canonical.description = description
                canonical.attributes.update({k: v for k, v in attributes.items() if v})
            else:
                entity_id = self._make_entity_id(name)
                canonical = CanonicalEntity(
                    entity_id=entity_id,
                    name=name,
                    entity_type=entity_type,
                    description=description,
                    aliases=aliases,
                    attributes=attributes,
                    first_seen_chunk=chunk_index,
                    last_seen_chunk=chunk_index,
                )
                self.canonical_entities[entity_id] = canonical
                existing_id = entity_id

            self._index_entity_names(existing_id, aliases)
            merged_entities[existing_id] = self.canonical_entities[existing_id]
        return list(merged_entities.values())

    def _merge_relationships(
        self,
        relationships: List[Dict[str, Any]],
        chunk_entities: List[CanonicalEntity],
        chunk_text: str,
        chunk_index: int,
    ) -> List[Dict[str, Any]]:
        chunk_entity_map = {entity.name: entity.entity_id for entity in chunk_entities}
        result = []
        for relation in relationships:
            source_name = (relation.get("source") or "").strip()
            target_name = (relation.get("target") or "").strip()
            if not source_name or not target_name:
                continue

            source_entity_id = self._find_entity_id_by_name(source_name, chunk_entity_map)
            target_entity_id = self._find_entity_id_by_name(target_name, chunk_entity_map)
            if not source_entity_id or not target_entity_id:
                continue

            relation_type = (relation.get("relation_type") or "INTERACTS_WITH").upper()
            key = (source_entity_id, relation_type, target_entity_id)
            description = (relation.get("description") or "").strip()
            evidence = self._extract_evidence(chunk_text, source_name, target_name)
            if key in self.relation_index:
                stored = self.relation_index[key]
                stored["occurrence_count"] += 1
                stored["last_seen_chunk"] = chunk_index
                stored["dirty"] = True
                if description and len(description) > len(stored.get("description", "")):
                    stored["description"] = description
                if evidence:
                    stored["evidence"] = evidence
                result.append(stored)
                continue

            row = {
                "edge_uuid": self._make_edge_id(source_entity_id, relation_type, target_entity_id),
                "source_entity_id": source_entity_id,
                "target_entity_id": target_entity_id,
                "relation_type": relation_type,
                "description": description,
                "evidence": evidence,
                "occurrence_count": 1,
                "first_seen_chunk": chunk_index,
                "last_seen_chunk": chunk_index,
                "dirty": True,
            }
            self.relation_index[key] = row
            result.append(row)
        return result

    def _evaluate_entity_lifecycle(
        self,
        chunk_entities: List[CanonicalEntity],
        chunk_relationships: List[Dict[str, Any]],
        chunk_index: int,
    ) -> Tuple[List[CanonicalEntity], List[Dict[str, Any]], set[str]]:
        touched_ids = {entity.entity_id for entity in chunk_entities}
        for relation in chunk_relationships:
            touched_ids.add(relation["source_entity_id"])
            touched_ids.add(relation["target_entity_id"])
            source = self.canonical_entities.get(relation["source_entity_id"])
            target = self.canonical_entities.get(relation["target_entity_id"])
            if source and target:
                if source.entity_type in CORE_ENTITY_TYPES or source.state == "active":
                    target.connected_core_count += 1
                if target.entity_type in CORE_ENTITY_TYPES or target.state == "active":
                    source.connected_core_count += 1

        changed_entities: List[CanonicalEntity] = []
        state_changes: List[Dict[str, Any]] = []

        for entity in self.canonical_entities.values():
            previous_state = entity.state
            entity.importance_score = self._score_entity(entity)

            if entity.entity_id in touched_ids and self._should_activate(entity):
                entity.state = "active"
                entity.archive_reason = ""
            elif previous_state == "active" and self._should_dormant(entity, chunk_index):
                entity.state = "dormant"
                entity.archive_reason = "inactive_low_value"
                self.archived_snapshots[entity.entity_id] = entity.to_row()
            elif previous_state == "dormant" and entity.entity_id in touched_ids and self._should_activate(entity):
                entity.state = "active"
                entity.archive_reason = ""
            elif previous_state != "active" and not self._should_activate(entity):
                entity.state = "candidate" if entity.appearance_count <= 1 else previous_state

            if entity.state != previous_state or entity.entity_id in touched_ids:
                if entity.state in {"active", "dormant"}:
                    changed_entities.append(entity)
                if entity.state != previous_state:
                    state_changes.append(
                        {
                            "entity_id": entity.entity_id,
                            "name": entity.name,
                            "from": previous_state,
                            "to": entity.state,
                            "importance_score": round(entity.importance_score, 2),
                            "reason": entity.archive_reason or "importance_reached_threshold",
                        }
                    )
        return changed_entities, state_changes, touched_ids

    def _collect_syncable_relationships(self, touched_ids: set[str]) -> List[Dict[str, Any]]:
        syncable = []
        for relation in self.relation_index.values():
            source = self.canonical_entities.get(relation["source_entity_id"])
            target = self.canonical_entities.get(relation["target_entity_id"])
            if not source or not target:
                continue
            if source.state != "active" or target.state != "active":
                continue
            if relation.get("dirty") or relation["source_entity_id"] in touched_ids or relation["target_entity_id"] in touched_ids:
                relation["dirty"] = False
                syncable.append(relation)
        return syncable

    def _score_entity(self, entity: CanonicalEntity) -> float:
        score = 0.0
        score += min(entity.appearance_count * 0.8, 3.2)
        score += min(entity.connected_core_count * 0.6, 2.4)
        score += min(len(entity.aliases) * 0.15, 0.6)
        if entity.description:
            score += 0.4
        if entity.entity_type in CORE_ENTITY_TYPES:
            score += 0.8
        if entity.attributes.get("identity") or entity.attributes.get("stage"):
            score += 0.4
        if len(entity.name) <= 1:
            score -= 0.6
        return max(score, 0.0)

    def _should_activate(self, entity: CanonicalEntity) -> bool:
        if entity.importance_score >= MIN_ACTIVE_IMPORTANCE:
            return True
        if entity.appearance_count >= 2:
            return True
        if entity.connected_core_count > 0 and entity.appearance_count >= 1:
            return True
        return False

    def _should_dormant(self, entity: CanonicalEntity, chunk_index: int) -> bool:
        if chunk_index - entity.last_seen_chunk < DORMANT_AFTER_CHUNKS:
            return False
        if entity.importance_score > DORMANT_MAX_IMPORTANCE:
            return False
        return entity.appearance_count <= 2 and entity.connected_core_count <= 1

    def _resolve_existing_entity_id(
        self,
        *,
        name: str,
        entity_type: str,
        description: str,
        aliases: set[str],
        attributes: Dict[str, Any],
    ) -> Optional[str]:
        normalized_names = {self._normalize_name(value) for value in aliases if value}
        for normalized in normalized_names:
            if normalized in self.entity_name_index:
                return self.entity_name_index[normalized]

        candidates = []
        for entity_id, canonical in self.canonical_entities.items():
            if canonical.entity_type != entity_type and entity_type != "Unknown" and canonical.entity_type != "Unknown":
                continue
            score = max(
                SequenceMatcher(None, self._normalize_name(name), self._normalize_name(canonical.name)).ratio(),
                *[
                    SequenceMatcher(None, self._normalize_name(name), self._normalize_name(alias)).ratio()
                    for alias in canonical.aliases
                ],
            )
            if score >= 0.72:
                candidates.append((score, entity_id, canonical))

        candidates.sort(key=lambda item: item[0], reverse=True)
        if not candidates:
            return None
        best_score, entity_id, canonical = candidates[0]
        if best_score >= 0.9:
            return entity_id

        decision = self._llm_merge_decision(name, entity_type, description, attributes, candidates[:3])
        if decision.get("decision") == "existing" and decision.get("entity_id"):
            return decision["entity_id"]
        if decision.get("decision") == "existing":
            return entity_id
        return None

    def _llm_merge_decision(
        self,
        name: str,
        entity_type: str,
        description: str,
        attributes: Dict[str, Any],
        candidates: List[tuple[float, str, CanonicalEntity]],
    ) -> Dict[str, Any]:
        prompt = {
            "new_entity": {
                "name": name,
                "entity_type": entity_type,
                "description": description,
                "attributes": attributes,
            },
            "candidates": [
                {
                    "entity_id": entity_id,
                    "name": canonical.name,
                    "entity_type": canonical.entity_type,
                    "description": canonical.description,
                    "aliases": sorted(canonical.aliases),
                    "attributes": canonical.attributes,
                }
                for _, entity_id, canonical in candidates
            ],
        }
        try:
            return self.llm_client.chat_json(
                messages=[
                    {"role": "system", "content": MERGE_DECISION_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                temperature=0.0,
                max_tokens=512,
            )
        except Exception:
            return {"decision": "new"}

    def _index_entity_names(self, entity_id: str, aliases: set[str]) -> None:
        for alias in aliases:
            normalized = self._normalize_name(alias)
            if normalized:
                self.entity_name_index[normalized] = entity_id

    def _find_entity_id_by_name(self, name: str, chunk_entity_map: Dict[str, str]) -> Optional[str]:
        if name in chunk_entity_map:
            return chunk_entity_map[name]
        return self.entity_name_index.get(self._normalize_name(name))

    def _extract_evidence(self, chunk_text: str, source_name: str, target_name: str) -> str:
        pattern = re.compile(rf"([^\n。！？]*{re.escape(source_name)}[^\n。！？]*{re.escape(target_name)}[^\n。！？]*[。！？]?)")
        match = pattern.search(chunk_text)
        if match:
            return match.group(1).strip()[:240]
        return chunk_text[:200].strip()

    def _make_entity_id(self, name: str) -> str:
        return f"entity_{hashlib.md5(name.encode('utf-8')).hexdigest()[:12]}"

    def _make_edge_id(self, source_entity_id: str, relation_type: str, target_entity_id: str) -> str:
        raw = f"{source_entity_id}:{relation_type}:{target_entity_id}"
        return f"edge_{hashlib.md5(raw.encode('utf-8')).hexdigest()[:12]}"

    def _normalize_name(self, value: str) -> str:
        return re.sub(r"[\W_]+", "", value or "").lower()
