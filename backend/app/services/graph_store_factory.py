"""
图谱存储工厂
"""

from ..config import Config
from .neo4j_graph_store import Neo4jGraphStore
from .zep_graph_store import ZepGraphStore


def create_graph_store():
    provider = getattr(Config, "GRAPH_STORE_PROVIDER", "zep").lower()
    if provider == "neo4j":
        return Neo4jGraphStore()
    if provider == "zep":
        return ZepGraphStore()
    raise ValueError(f"不支持的图谱存储提供方: {provider}")
