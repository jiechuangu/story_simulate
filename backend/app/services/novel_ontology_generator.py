"""
小说世界分块本体生成器
"""

from __future__ import annotations

from collections import Counter
import math
import json
import os
from typing import Any, Dict, List, Optional

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .text_processor import TextProcessor


CHUNK_EXTRACTION_SYSTEM_PROMPT = """你是小说世界知识图谱抽取器。

请从给定文本块中抽取对“小说世界模拟引擎”最有用的结构化信息。
只输出 JSON，不要解释，不要 markdown。

输出格式：
{
  "entities": [
    {
      "name": "实体名称",
      "entity_type": "Person|Faction|Location|Creature|Artifact|PowerSystem|Event|Organization|Family|Unknown",
      "description": "简要描述",
      "aliases": ["别名1", "别名2"],
      "attributes": {
        "appearance": "外貌或形象信息",
        "identity": "身份/职业/阵营",
        "stage": "当前阶段或演进形态"
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
  "observations": ["关键世界规则、时间推进线索、角色演进线索"]
}
"""

class NovelOntologyGenerator:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()
        self.logger = get_logger("mirofish.ontology")

    ONTOLOGY_CHUNK_SIZE = 1800
    ONTOLOGY_CHUNK_OVERLAP = 120
    ONTOLOGY_MAX_CHUNKS = 6

    def generate(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str] = None,
        output_dir: Optional[str] = None,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        combined_text = "\n\n".join(document_texts)
        all_chunks = TextProcessor.split_text(
            combined_text,
            chunk_size=self.ONTOLOGY_CHUNK_SIZE,
            overlap=self.ONTOLOGY_CHUNK_OVERLAP,
        )
        sample_chunks = self._select_sample_chunks(all_chunks)
        self.logger.info(
            "开始分块本体生成: 原始块数=%s, 采样块数=%s, 块大小=%s",
            len(all_chunks),
            len(sample_chunks),
            self.ONTOLOGY_CHUNK_SIZE,
        )
        if progress_callback:
            progress_callback(
                f"开始分块本体生成：0/{len(sample_chunks)}",
                10,
            )
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        extracted_samples = []
        for index, chunk in enumerate(sample_chunks):
            self.logger.info("本体子任务 %s/%s", index + 1, len(sample_chunks))
            if progress_callback:
                progress = 10 + int(((index) / max(len(sample_chunks), 1)) * 75)
                progress_callback(f"本体子任务 {index + 1}/{len(sample_chunks)}", progress)
            extracted = self._extract_chunk(
                chunk=chunk,
                chunk_index=index,
                simulation_requirement=simulation_requirement,
                additional_context=additional_context,
            )
            if output_dir:
                self._write_chunk_result(output_dir, index, chunk, extracted)
            extracted_samples.append(extracted)

        result = self._synthesize_ontology(extracted_samples, simulation_requirement, additional_context)
        if progress_callback:
            progress_callback("正在归并本体候选结果...", 92)
        if output_dir:
            self._write_summary_result(output_dir, result, extracted_samples)
        if progress_callback:
            progress_callback("本体生成完成", 100)
        return result

    def _select_sample_chunks(self, chunks: List[str]) -> List[str]:
        if len(chunks) <= self.ONTOLOGY_MAX_CHUNKS:
            return chunks

        indices = []
        for i in range(self.ONTOLOGY_MAX_CHUNKS):
            ratio = i / max(self.ONTOLOGY_MAX_CHUNKS - 1, 1)
            idx = min(len(chunks) - 1, math.floor(ratio * (len(chunks) - 1)))
            if idx not in indices:
                indices.append(idx)
        return [chunks[idx] for idx in indices]

    def _write_chunk_result(
        self,
        output_dir: str,
        chunk_index: int,
        chunk_text: str,
        extracted: Dict[str, Any],
    ) -> None:
        payload = {
            "chunk_index": chunk_index + 1,
            "chunk_length": len(chunk_text),
            "entity_count": len(extracted.get("entities", [])),
            "relationship_count": len(extracted.get("relationships", [])),
            "observation_count": len(extracted.get("observations", [])),
            "entity_type_top5": self._top_counts(
                [entity.get("entity_type", "Unknown") for entity in extracted.get("entities", [])]
            ),
            "relation_type_top5": self._top_counts(
                [relation.get("relation_type", "INTERACTS_WITH") for relation in extracted.get("relationships", [])]
            ),
            "preview": chunk_text[:300],
            "result": extracted,
        }
        path = os.path.join(output_dir, f"chunk_{chunk_index + 1:02d}.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    def _write_summary_result(
        self,
        output_dir: str,
        result: Dict[str, Any],
        extracted_samples: List[Dict[str, Any]],
    ) -> None:
        payload = {
            "chunk_count": len(extracted_samples),
            "entity_type_count": len(result.get("entity_types", [])),
            "edge_type_count": len(result.get("edge_types", [])),
            "analysis_summary": result.get("analysis_summary", ""),
            "ontology": result,
        }
        path = os.path.join(output_dir, "summary.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    def _top_counts(self, values: List[str]) -> List[Dict[str, Any]]:
        counter = Counter(value for value in values if value)
        return [{"name": name, "count": count} for name, count in counter.most_common(5)]

    def _extract_chunk(
        self,
        chunk: str,
        chunk_index: int,
        simulation_requirement: str,
        additional_context: Optional[str],
    ) -> Dict[str, Any]:
        user_prompt = f"""模拟需求：
{simulation_requirement}

额外说明：
{additional_context or "无"}

当前文本块编号：{chunk_index + 1}

文本块内容：
{chunk}
"""
        return self.llm_client.chat_json(
            messages=[
                {"role": "system", "content": CHUNK_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=1024,
        )

    def _synthesize_ontology(
        self,
        extracted_samples: List[Dict[str, Any]],
        simulation_requirement: str,
        additional_context: Optional[str],
    ) -> Dict[str, Any]:
        entity_type_counter: Counter[str] = Counter()
        relation_type_counter: Counter[str] = Counter()
        example_entities: Dict[str, List[str]] = {}
        observations: List[str] = []

        for sample in extracted_samples:
            for entity in sample.get("entities", []):
                entity_type = entity.get("entity_type", "Unknown")
                name = entity.get("name")
                entity_type_counter[entity_type] += 1
                if name:
                    example_entities.setdefault(entity_type, [])
                    if name not in example_entities[entity_type]:
                        example_entities[entity_type].append(name)

            for relation in sample.get("relationships", []):
                relation_type = relation.get("relation_type", "INTERACTS_WITH")
                relation_type_counter[relation_type] += 1

            observations.extend(sample.get("observations", []))

        entity_types = self._fallback_entity_types(entity_type_counter, example_entities)
        edge_types = self._fallback_edge_types(relation_type_counter)
        observation_lines = [item.strip() for item in observations if item and item.strip()]
        summary_parts = []
        if entity_type_counter:
            summary_parts.append(
                "高频实体类型: " +
                "、".join(f"{name}({count})" for name, count in entity_type_counter.most_common(5))
            )
        if relation_type_counter:
            summary_parts.append(
                "高频关系类型: " +
                "、".join(f"{name}({count})" for name, count in relation_type_counter.most_common(5))
            )
        if observation_lines:
            summary_parts.append("观察摘要: " + "；".join(observation_lines[:6]))
        if simulation_requirement:
            summary_parts.append(f"模拟目标: {simulation_requirement}")

        return {
            "entity_types": entity_types,
            "edge_types": edge_types,
            "analysis_summary": "\n".join(summary_parts) if summary_parts else "基于分块抽取结果生成的小说世界本体。",
        }

    def _fallback_entity_types(
        self,
        entity_type_counter: Counter[str],
        example_entities: Dict[str, List[str]],
    ) -> List[Dict[str, Any]]:
        results = []
        for entity_type, _ in entity_type_counter.most_common(8):
            name = "Character" if entity_type == "Person" else entity_type
            pascal_name = "".join(part.capitalize() for part in name.replace("_", " ").split())
            results.append(
                {
                    "name": pascal_name or "Entity",
                    "description": f"{pascal_name or 'Entity'} type for novel world simulation",
                    "attributes": [
                        {"name": "description", "type": "text", "description": "Core description"},
                        {"name": "appearance", "type": "text", "description": "Visual traits"},
                        {"name": "identity", "type": "text", "description": "Role or affiliation"},
                        {"name": "stage", "type": "text", "description": "Current evolution stage"},
                    ],
                    "examples": example_entities.get(entity_type, [])[:4],
                }
            )
        if not results:
            results = [
                {
                    "name": "Character",
                    "description": "Primary character in the novel world",
                    "attributes": [
                        {"name": "description", "type": "text", "description": "Core description"},
                        {"name": "appearance", "type": "text", "description": "Visual traits"},
                        {"name": "identity", "type": "text", "description": "Role or affiliation"},
                        {"name": "stage", "type": "text", "description": "Current evolution stage"},
                    ],
                    "examples": [],
                },
                {
                    "name": "Location",
                    "description": "Place in the novel world",
                    "attributes": [
                        {"name": "description", "type": "text", "description": "Core description"},
                        {"name": "region", "type": "text", "description": "Region or area"},
                    ],
                    "examples": [],
                },
            ]
        return results

    def _fallback_edge_types(self, relation_type_counter: Counter[str]) -> List[Dict[str, Any]]:
        results = []
        for relation_type, _ in relation_type_counter.most_common(8):
            results.append(
                {
                    "name": relation_type.upper(),
                    "description": f"{relation_type.upper()} relationship in the story world",
                    "source_targets": [{"source": "Character", "target": "Character"}],
                    "attributes": [],
                }
            )
        if not results:
            results = [
                {
                    "name": "INTERACTS_WITH",
                    "description": "Interaction relationship in the story world",
                    "source_targets": [{"source": "Character", "target": "Character"}],
                    "attributes": [],
                },
                {
                    "name": "LOCATED_IN",
                    "description": "Location relationship in the story world",
                    "source_targets": [{"source": "Character", "target": "Location"}],
                    "attributes": [],
                },
            ]
        return results
