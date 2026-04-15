"""
Neo4j Aura 图谱存储适配器
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase

from ..config import Config
from .graph_store import GraphStore


class Neo4jGraphStore(GraphStore):
    def __init__(
        self,
        uri: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
    ):
        self.uri = uri or Config.NEO4J_URI
        self.username = username or Config.NEO4J_USERNAME
        self.password = password or Config.NEO4J_PASSWORD
        self.database = database or Config.NEO4J_DATABASE or None

        if not self.uri or not self.username or not self.password:
            raise ValueError("Neo4j Aura 配置不完整")

        self.driver = GraphDatabase.driver(
            self.uri,
            auth=(self.username, self.password),
        )

    def create_graph(self, name: str, description: str = "") -> str:
        graph_id = f"mirofish_{uuid.uuid4().hex[:16]}"
        now = datetime.utcnow().isoformat()
        query = """
        MERGE (g:Graph {graph_id: $graph_id})
        SET g.name = $name,
            g.description = $description,
            g.provider = 'neo4j',
            g.created_at = $now,
            g.updated_at = $now
        """
        self._run(query, graph_id=graph_id, name=name, description=description, now=now)
        return graph_id

    def touch_graph(self, graph_id: str) -> None:
        self._run(
            """
            MATCH (g:Graph {graph_id: $graph_id})
            SET g.updated_at = $now
            """,
            graph_id=graph_id,
            now=datetime.utcnow().isoformat(),
        )

    def upsert_entities(self, graph_id: str, entities: List[Dict[str, Any]], chunk_index: int) -> None:
        if not entities:
            return
        rows = []
        for entity in entities:
            aliases = sorted({alias for alias in entity.get("aliases", []) if alias})
            rows.append(
                {
                    "graph_id": graph_id,
                    "entity_id": entity["entity_id"],
                    "name": entity["name"],
                    "entity_type": entity.get("entity_type", "Entity"),
                    "description": entity.get("description", ""),
                    "status_summary": entity.get("status_summary", ""),
                    "aliases_json": json.dumps(aliases, ensure_ascii=False),
                    "attributes_json": json.dumps(entity.get("attributes", {}), ensure_ascii=False),
                    "appearance_count": int(entity.get("appearance_count", 1)),
                    "importance_score": float(entity.get("importance_score", 0)),
                    "connected_core_count": int(entity.get("connected_core_count", 0)),
                    "state": entity.get("state", "active"),
                    "archive_reason": entity.get("archive_reason", ""),
                    "first_seen_chunk": int(entity.get("first_seen_chunk", chunk_index)),
                    "last_seen_chunk": int(entity.get("last_seen_chunk", chunk_index)),
                    "updated_at": datetime.utcnow().isoformat(),
                }
            )

        query = """
        UNWIND $rows AS row
        MERGE (e:Entity {graph_id: row.graph_id, entity_id: row.entity_id})
        ON CREATE SET
            e.uuid = row.entity_id,
            e.created_at = row.updated_at,
            e.first_seen_chunk = row.first_seen_chunk
        SET
            e.name = row.name,
            e.entity_type = row.entity_type,
            e.description = row.description,
            e.status_summary = row.status_summary,
            e.aliases_json = row.aliases_json,
            e.attributes_json = row.attributes_json,
            e.appearance_count = row.appearance_count,
            e.importance_score = row.importance_score,
            e.connected_core_count = row.connected_core_count,
            e.state = row.state,
            e.archive_reason = row.archive_reason,
            e.last_seen_chunk = row.last_seen_chunk,
            e.updated_at = row.updated_at
        WITH row, e
        MATCH (g:Graph {graph_id: row.graph_id})
        MERGE (g)-[:HAS_ENTITY]->(e)
        """
        self._run(query, rows=rows)
        self.touch_graph(graph_id)

    def upsert_relationships(self, graph_id: str, relationships: List[Dict[str, Any]], chunk_index: int) -> None:
        if not relationships:
            return
        rows = []
        for relation in relationships:
            rows.append(
                {
                    "graph_id": graph_id,
                    "edge_uuid": relation.get("edge_uuid") or uuid.uuid4().hex,
                    "source_entity_id": relation["source_entity_id"],
                    "target_entity_id": relation["target_entity_id"],
                    "relation_type": relation.get("relation_type", "RELATED_TO"),
                    "description": relation.get("description", ""),
                    "evidence": relation.get("evidence", ""),
                    "occurrence_count": int(relation.get("occurrence_count", 1)),
                    "first_seen_chunk": int(relation.get("first_seen_chunk", chunk_index)),
                    "last_seen_chunk": int(relation.get("last_seen_chunk", chunk_index)),
                    "updated_at": datetime.utcnow().isoformat(),
                }
            )

        query = """
        UNWIND $rows AS row
        MATCH (s:Entity {graph_id: row.graph_id, entity_id: row.source_entity_id})
        MATCH (t:Entity {graph_id: row.graph_id, entity_id: row.target_entity_id})
        MERGE (s)-[r:RELATES_TO {graph_id: row.graph_id, relation_type: row.relation_type, target_entity_id: row.target_entity_id}]->(t)
        ON CREATE SET
            r.uuid = row.edge_uuid,
            r.created_at = row.updated_at,
            r.first_seen_chunk = row.first_seen_chunk,
            r.occurrence_count = 0
        SET
            r.description = row.description,
            r.evidence = row.evidence,
            r.occurrence_count = coalesce(r.occurrence_count, 0) + row.occurrence_count,
            r.last_seen_chunk = row.last_seen_chunk,
            r.updated_at = row.updated_at
        """
        self._run(query, rows=rows)
        self.touch_graph(graph_id)

    def get_graph_data(self, graph_id: str, include_inactive: bool = False) -> Dict[str, Any]:
        node_where = "" if include_inactive else "AND coalesce(e.state, 'active') = 'active'"
        edge_where = "" if include_inactive else (
            "AND coalesce(s.state, 'active') = 'active' "
            "AND coalesce(t.state, 'active') = 'active'"
        )
        node_records = self._run_fetchall(
            f"""
            MATCH (:Graph {{graph_id: $graph_id}})-[:HAS_ENTITY]->(e:Entity {{graph_id: $graph_id}})
            WHERE 1 = 1 {node_where}
            RETURN e
            ORDER BY coalesce(e.importance_score, 0) DESC, e.appearance_count DESC, e.name ASC
            """,
            graph_id=graph_id,
        )
        edge_records = self._run_fetchall(
            f"""
            MATCH (s:Entity {{graph_id: $graph_id}})-[r:RELATES_TO {{graph_id: $graph_id}}]->(t:Entity {{graph_id: $graph_id}})
            WHERE 1 = 1 {edge_where}
            RETURN s, properties(r) AS r_props, type(r) AS r_type, t
            ORDER BY r.occurrence_count DESC, r.updated_at DESC
            """,
            graph_id=graph_id,
        )

        nodes = [self._serialize_entity(record["e"]) for record in node_records]
        edges = [self._serialize_edge(record["s"], record["r_props"], record["r_type"], record["t"]) for record in edge_records]
        return {
            "graph_id": graph_id,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": nodes,
            "edges": edges,
        }

    def delete_graph(self, graph_id: str) -> None:
        self._run(
            """
            MATCH (g:Graph {graph_id: $graph_id})
            OPTIONAL MATCH (g)-[:HAS_ENTITY]->(e:Entity {graph_id: $graph_id})
            DETACH DELETE g, e
            """,
            graph_id=graph_id,
        )

    def get_entity_snapshot(self, graph_id: str, entity_id: str) -> Optional[Dict[str, Any]]:
        records = self._run_fetchall(
            """
            MATCH (e:Entity {graph_id: $graph_id, entity_id: $entity_id})
            RETURN e
            LIMIT 1
            """,
            graph_id=graph_id,
            entity_id=entity_id,
        )
        if not records:
            return None
        entity = self._serialize_entity(records[0]["e"])
        neighbors = self.get_neighbors(graph_id, entity_id, limit=10)
        entity["related_nodes"] = neighbors
        return entity

    def get_neighbors(self, graph_id: str, entity_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        records = self._run_fetchall(
            """
            MATCH (e:Entity {graph_id: $graph_id, entity_id: $entity_id})-[r:RELATES_TO {graph_id: $graph_id}]-(n:Entity {graph_id: $graph_id})
            RETURN n, properties(r) AS r_props, type(r) AS r_type
            ORDER BY r.occurrence_count DESC, r.updated_at DESC
            LIMIT $limit
            """,
            graph_id=graph_id,
            entity_id=entity_id,
            limit=limit,
        )
        result = []
        for record in records:
            neighbor = self._serialize_entity(record["n"])
            neighbor["relationship"] = {
                "type": record.get("r_type") or record["r_props"].get("relation_type"),
                "description": record["r_props"].get("description"),
            }
            result.append(neighbor)
        return result

    def search_facts(self, graph_id: str, query: str, limit: int = 10) -> List[str]:
        records = self._run_fetchall(
            """
            MATCH (s:Entity {graph_id: $graph_id})-[r:RELATES_TO {graph_id: $graph_id}]->(t:Entity {graph_id: $graph_id})
            WHERE toLower(coalesce(r.description, '')) CONTAINS toLower($search_query)
               OR toLower(coalesce(r.evidence, '')) CONTAINS toLower($search_query)
               OR toLower(coalesce(s.name, '')) CONTAINS toLower($search_query)
               OR toLower(coalesce(t.name, '')) CONTAINS toLower($search_query)
            RETURN s.name AS source_name, r.relation_type AS relation_type, t.name AS target_name, r.description AS description
            LIMIT $limit
            """,
            graph_id=graph_id,
            search_query=query,
            limit=limit,
        )
        return [
            f"{record['source_name']} -[{record['relation_type']}]-> {record['target_name']}: {record['description'] or ''}".strip()
            for record in records
        ]

    def _serialize_entity(self, node: Any) -> Dict[str, Any]:
        aliases = self._safe_json_loads(node.get("aliases_json"), [])
        attributes = self._safe_json_loads(node.get("attributes_json"), {})
        entity_type = node.get("entity_type") or "Entity"
        labels = ["Entity"]
        if entity_type not in labels:
            labels.append(entity_type)
        return {
            "uuid": node.get("uuid") or node.get("entity_id"),
            "entity_id": node.get("entity_id"),
            "name": node.get("name"),
            "labels": labels,
            "summary": node.get("status_summary") or node.get("description"),
            "attributes": {
                **attributes,
                "aliases": aliases,
                "appearance_count": node.get("appearance_count", 1),
                "importance_score": node.get("importance_score", 0),
                "connected_core_count": node.get("connected_core_count", 0),
                "first_seen_chunk": node.get("first_seen_chunk"),
                "last_seen_chunk": node.get("last_seen_chunk"),
                "archive_reason": node.get("archive_reason"),
            },
            "state": node.get("state", "active"),
            "created_at": node.get("created_at"),
            "updated_at": node.get("updated_at"),
        }

    def _serialize_edge(self, source: Any, relation: Any, relation_type: str, target: Any) -> Dict[str, Any]:
        return {
            "uuid": relation.get("uuid"),
            "name": relation_type or relation.get("relation_type"),
            "fact_type": relation_type or relation.get("relation_type"),
            "fact": relation.get("description") or relation.get("evidence"),
            "source_node_uuid": source.get("uuid") or source.get("entity_id"),
            "target_node_uuid": target.get("uuid") or target.get("entity_id"),
            "source_name": source.get("name"),
            "target_name": target.get("name"),
            "created_at": relation.get("created_at"),
            "valid_at": relation.get("created_at"),
            "attributes": {
                "occurrence_count": relation.get("occurrence_count", 1),
                "first_seen_chunk": relation.get("first_seen_chunk"),
                "last_seen_chunk": relation.get("last_seen_chunk"),
                "evidence": relation.get("evidence"),
            },
        }

    def _safe_json_loads(self, value: Optional[str], default: Any) -> Any:
        if not value:
            return default
        try:
            return json.loads(value)
        except Exception:
            return default

    def _run(self, query: str, **params: Any) -> None:
        session_kwargs: Dict[str, Any] = {}
        if self.database:
            session_kwargs["database"] = self.database
        with self.driver.session(**session_kwargs) as session:
            session.run(query, **params).consume()

    def _run_fetchall(self, query: str, **params: Any) -> List[Dict[str, Any]]:
        session_kwargs: Dict[str, Any] = {}
        if self.database:
            session_kwargs["database"] = self.database
        with self.driver.session(**session_kwargs) as session:
            result = session.run(query, **params)
            return [record.data() for record in result]
