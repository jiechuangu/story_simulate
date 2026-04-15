"""
图谱存储抽象层

为未来从 Zep 迁移到 Neo4j 预留兼容接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class GraphStore(ABC):
    @abstractmethod
    def get_entity_snapshot(self, graph_id: str, entity_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_neighbors(self, graph_id: str, entity_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def search_facts(self, graph_id: str, query: str, limit: int = 10) -> List[str]:
        raise NotImplementedError
