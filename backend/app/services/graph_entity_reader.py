"""
统一图谱实体读取服务

在 simulation / profile 相关链路中屏蔽 Zep 与 Neo4j 的差异。
"""

from __future__ import annotations

from typing import List, Optional, Set

from ..config import Config
from ..utils.logger import get_logger
from .graph_store_factory import create_graph_store
from .neo4j_graph_store import Neo4jGraphStore
from .zep_entity_reader import EntityNode, FilteredEntities, ZepEntityReader

logger = get_logger("mirofish.graph_entity_reader")


class GraphEntityReader:
    def __init__(self):
        self.provider = getattr(Config, "GRAPH_STORE_PROVIDER", "zep").lower()
        self._zep_reader = ZepEntityReader() if self.provider == "zep" else None
        self._graph_store = create_graph_store()

    def filter_defined_entities(
        self,
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True,
    ) -> FilteredEntities:
        if self.provider == "zep":
            return self._zep_reader.filter_defined_entities(
                graph_id=graph_id,
                defined_entity_types=defined_entity_types,
                enrich_with_edges=enrich_with_edges,
            )
        return self._filter_neo4j_entities(
            graph_id=graph_id,
            defined_entity_types=defined_entity_types,
            enrich_with_edges=enrich_with_edges,
        )

    def get_entity_with_context(self, graph_id: str, entity_uuid: str) -> Optional[EntityNode]:
        if self.provider == "zep":
            return self._zep_reader.get_entity_with_context(graph_id, entity_uuid)

        snapshot = self._graph_store.get_entity_snapshot(graph_id, entity_uuid)
        if not snapshot:
            return None
        return self._entity_from_snapshot(snapshot, enrich_with_edges=True)

    def get_entities_by_type(
        self,
        graph_id: str,
        entity_type: str,
        enrich_with_edges: bool = True,
    ) -> List[EntityNode]:
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges,
        )
        return result.entities

    def _filter_neo4j_entities(
        self,
        graph_id: str,
        defined_entity_types: Optional[List[str]],
        enrich_with_edges: bool,
    ) -> FilteredEntities:
        if not isinstance(self._graph_store, Neo4jGraphStore):
            raise ValueError(f"当前 provider={self.provider} 不支持该读取路径")

        graph_data = self._graph_store.get_graph_data(graph_id, include_inactive=False)
        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])
        total_count = len(nodes)

        edge_map = {}
        if enrich_with_edges:
            for edge in edges:
                source_id = edge.get("source_node_uuid")
                target_id = edge.get("target_node_uuid")
                if source_id:
                    edge_map.setdefault(source_id, []).append(edge)
                if target_id:
                    edge_map.setdefault(target_id, []).append(edge)

        filtered_entities: List[EntityNode] = []
        entity_types_found: Set[str] = set()

        for node in nodes:
            labels = node.get("labels", [])
            custom_labels = [label for label in labels if label not in ["Entity", "Node"]]
            if not custom_labels:
                continue

            if defined_entity_types:
                matching = [label for label in custom_labels if label in defined_entity_types]
                if not matching:
                    continue
                entity_type = matching[0]
            else:
                entity_type = custom_labels[0]

            entity_types_found.add(entity_type)
            entity = self._entity_from_snapshot(node, enrich_with_edges=False)

            if enrich_with_edges:
                related_edges = []
                related_nodes = []
                seen_related = set()
                for edge in edge_map.get(node.get("uuid"), []):
                    if edge.get("source_node_uuid") == node.get("uuid"):
                        related_uuid = edge.get("target_node_uuid")
                        direction = "outgoing"
                    else:
                        related_uuid = edge.get("source_node_uuid")
                        direction = "incoming"
                    related_edges.append(
                        {
                            "direction": direction,
                            "edge_name": edge.get("name"),
                            "fact": edge.get("fact"),
                            "target_node_uuid": edge.get("target_node_uuid"),
                            "source_node_uuid": edge.get("source_node_uuid"),
                        }
                    )
                    if related_uuid and related_uuid not in seen_related:
                        seen_related.add(related_uuid)
                        related = next((n for n in nodes if n.get("uuid") == related_uuid), None)
                        if related:
                            related_nodes.append(
                                {
                                    "uuid": related.get("uuid"),
                                    "name": related.get("name"),
                                    "labels": related.get("labels", []),
                                    "summary": related.get("summary", ""),
                                }
                            )
                entity.related_edges = related_edges
                entity.related_nodes = related_nodes

            filtered_entities.append(entity)

        logger.info(
            "Neo4j实体筛选完成: graph=%s total=%s filtered=%s types=%s",
            graph_id,
            total_count,
            len(filtered_entities),
            entity_types_found,
        )
        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )

    def _entity_from_snapshot(self, snapshot: dict, enrich_with_edges: bool) -> EntityNode:
        related_nodes = snapshot.get("related_nodes", []) if enrich_with_edges else []
        return EntityNode(
            uuid=snapshot.get("uuid") or snapshot.get("entity_id") or "",
            name=snapshot.get("name") or "",
            labels=snapshot.get("labels", []),
            summary=snapshot.get("summary") or "",
            attributes=snapshot.get("attributes", {}),
            related_edges=snapshot.get("related_edges", []),
            related_nodes=related_nodes,
        )
