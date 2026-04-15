"""
Zep 图谱存储适配器
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .graph_store import GraphStore
from .zep_entity_reader import ZepEntityReader
from .zep_tools import ZepToolsService


class ZepGraphStore(GraphStore):
    def __init__(self):
        self.reader = ZepEntityReader()
        self.tools = ZepToolsService()

    def get_entity_snapshot(self, graph_id: str, entity_id: str) -> Optional[Dict[str, Any]]:
        entity = self.reader.get_entity_with_context(graph_id, entity_id)
        return entity.to_dict() if entity else None

    def get_neighbors(self, graph_id: str, entity_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        entity = self.reader.get_entity_with_context(graph_id, entity_id)
        if not entity:
            return []
        return (entity.related_nodes or [])[:limit]

    def search_facts(self, graph_id: str, query: str, limit: int = 10) -> List[str]:
        result = self.tools.quick_search(graph_id=graph_id, query=query, limit=limit)
        return result.facts[:limit] if result else []
