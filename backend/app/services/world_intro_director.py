"""
角色引导页导演器（Step5 -> Step6）

功能：
1. 结合图谱事实与时间线，生成 3~10 页角色背景引导
2. 每页文案由 LLM 重写，不使用前端模板拼接
3. 返回每页对应知识来源，供前端展示
"""

from __future__ import annotations

import concurrent.futures
import re
from typing import Any, Dict, List, Optional

from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .graph_store_factory import create_graph_store
from .world_engine import WorldEngine

logger = get_logger("mirofish.world_intro_director")


def _clip(text: str, max_len: int = 280) -> str:
    value = (text or "").strip()
    if len(value) <= max_len:
        return value
    return value[: max_len - 3] + "..."


def _clean_source_text(source: str) -> str:
    text = (source or "").strip()
    if not text:
        return ""
    # 去掉形如 [世界] / [时间线] / [图谱] 的标签，避免直接像提示词拼接
    text = re.sub(r"^\[[^\]]+\]\s*", "", text)
    text = text.replace("->", "与")
    text = re.sub(r"\s+", " ", text).strip()
    return text


class WorldIntroDirector:
    LLM_TIMEOUT_SECONDS = 30

    def __init__(self):
        self._engine = WorldEngine()
        self._llm: Optional[LLMClient] = None

    def build_intro(self, simulation_id: str, character_id: str) -> Dict[str, Any]:
        state = self._engine.get_world(simulation_id)
        if not state:
            raise ValueError(f"世界状态不存在: {simulation_id}")
        if not character_id:
            raise ValueError("缺少 character_id")

        role = next((c for c in state.characters if c.character_id == character_id), None)
        if not role:
            raise ValueError(f"角色不存在: {character_id}")

        source_pool = self._build_source_pool(state, role)
        fallback_count = self._fallback_slide_count(source_pool)
        generated = self._llm_generate(state, role, source_pool, fallback_count)

        if not generated:
            logger.info("角色引导使用回退生成: simulation=%s character=%s reason=llm_failed_or_invalid", simulation_id, character_id)
            return self._fallback_intro(state, role, source_pool, fallback_count)

        slide_count = int(generated.get("slide_count", fallback_count) or fallback_count)
        slide_count = max(3, min(10, slide_count))
        raw_slides = generated.get("slides") or []

        normalized_slides: List[Dict[str, Any]] = []
        for idx in range(slide_count):
            raw = raw_slides[idx] if idx < len(raw_slides) and isinstance(raw_slides[idx], dict) else {}
            title = _clip(str(raw.get("title") or f"章节 {idx + 1}"), 60)
            text = _clip(str(raw.get("text") or self._fallback_slide_text(role, source_pool, idx, slide_count)), 420)
            source_indices = raw.get("source_indices") or []
            if not isinstance(source_indices, list):
                source_indices = []
            safe_indices = []
            for item in source_indices:
                try:
                    value = int(item)
                except Exception:
                    continue
                if 0 <= value < len(source_pool) and value not in safe_indices:
                    safe_indices.append(value)
            if not safe_indices and source_pool:
                safe_indices = [idx % len(source_pool)]
            normalized_slides.append(
                {
                    "index": idx,
                    "title": title,
                    "text": text,
                    "sources": [source_pool[i] for i in safe_indices][:4],
                }
            )

        # 末页强制收束到“玩家即将进入”
        if normalized_slides:
            last = normalized_slides[-1]
            last["text"] = _clip(
                f"{last['text']} 当前地点：{role.current_location or '未知地点'}。当前目标：{role.current_goal or '观察局势'}。你将以该角色视角进入世界。",
                420,
            )

        return {
            "character_id": role.character_id,
            "character_name": role.name,
            "slide_count": len(normalized_slides),
            "slides": normalized_slides,
            "generation_mode": "llm",
        }

    def _build_source_pool(self, state, role) -> List[str]:
        pool: List[str] = []
        timeline_related = [
            event for event in (state.timeline_events or [])
            if role.character_id in (event.related_character_ids or [])
        ][:24]
        for event in timeline_related:
            line = _clip(f"[时间线] {event.title}: {event.description}", 220)
            if line and line not in pool:
                pool.append(line)

        for event in (state.timeline_events or [])[:10]:
            line = _clip(f"[世界] {event.title}: {event.description}", 200)
            if line and line not in pool:
                pool.append(line)

        try:
            store = create_graph_store()
            name = (role.name or "").split("_")[0].strip()
            for query in [name, role.name]:
                if not query:
                    continue
                facts = store.search_facts(state.graph_id, query=query, limit=20)
                for fact in facts:
                    line = _clip(f"[图谱] {fact}", 220)
                    if line and line not in pool:
                        pool.append(line)
        except Exception as exc:
            logger.warning("角色引导图谱检索失败: %s", exc)

        if not pool:
            pool = [
                _clip(f"[角色] {role.name}: {role.summary or role.persona or '暂无摘要'}", 220),
                _clip(f"[状态] 地点：{role.current_location or '未知'}；目标：{role.current_goal or '观察局势'}", 220),
            ]
        return pool[:48]

    def _fallback_slide_count(self, source_pool: List[str]) -> int:
        size = len(source_pool)
        if size <= 6:
            return 3
        if size <= 12:
            return 4
        if size <= 18:
            return 5
        if size <= 24:
            return 6
        if size <= 32:
            return 8
        return 10

    def _llm_generate(self, state, role, source_pool: List[str], fallback_count: int) -> Optional[Dict[str, Any]]:
        try:
            if self._llm is None:
                self._llm = LLMClient()
            payload = {
                "world_name": state.world_name,
                "world_requirement": _clip(state.simulation_requirement, 360),
                "character_name": role.name,
                "character_summary": _clip(role.summary or role.persona, 320),
                "character_location": role.current_location,
                "character_goal": role.current_goal,
                "expected_slide_count_hint": fallback_count,
                "source_pool": source_pool[:30],
            }

            def _run() -> Dict[str, Any]:
                return self._llm.chat_json(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "你是剧情导演。请基于给定知识源，输出角色进入世界前的图文引导脚本。"
                                "必须返回严格 JSON，键为：slide_count, slides。"
                                "slide_count 必须是 3 到 10 的整数。"
                                "slides 是数组，长度应等于 slide_count。"
                                "每个 slide 对象必须包含：title, text, source_indices。"
                                "source_indices 是 source_pool 的下标数组（整数）。"
                                "要求：按时间从远到近组织叙事，最后一页必须收束到“当前正在何处、准备做什么、即将由玩家接管”。"
                                "文风自然，不要模板化短句。不要输出 markdown。"
                            ),
                        },
                        {"role": "user", "content": str(payload)},
                    ],
                    temperature=0.65,
                    max_tokens=1500,
                )

            ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = ex.submit(_run)
            try:
                result = future.result(timeout=self.LLM_TIMEOUT_SECONDS)
            finally:
                ex.shutdown(wait=False, cancel_futures=True)

            if not isinstance(result, dict):
                return None
            return result
        except concurrent.futures.TimeoutError:
            logger.warning("角色引导 LLM 调用超时(%ss)，回退规则生成", self.LLM_TIMEOUT_SECONDS)
            return None
        except Exception as exc:
            logger.warning("角色引导 LLM 生成失败，使用回退逻辑: %s", exc)
            return None

    def _fallback_slide_text(self, role, source_pool: List[str], idx: int, total: int) -> str:
        source = _clean_source_text(source_pool[idx % len(source_pool)]) if source_pool else ""
        if source:
            source_line = f"已知线索显示：{source}。"
        else:
            source_line = "相关线索仍在收敛中。"
        if idx == total - 1:
            return (
                f"{role.name} 的经历已经汇聚到当前节点。{source_line} "
                f"此刻他/她位于{role.current_location or '未知地点'}，并围绕“{role.current_goal or '观察局势'}”准备行动。"
            )
        return (
            f"{role.name} 的故事进入新的阶段。{source_line}"
            "局势中的人物关系和行动目标正在发生变化。"
        )

    def _fallback_intro(self, state, role, source_pool: List[str], count: int) -> Dict[str, Any]:
        slides: List[Dict[str, Any]] = []
        for idx in range(count):
            slides.append(
                {
                    "index": idx,
                    "title": f"章节 {idx + 1}",
                    "text": _clip(self._fallback_slide_text(role, source_pool, idx, count), 420),
                    "sources": [source_pool[idx % len(source_pool)]] if source_pool else [],
                }
            )
        return {
            "character_id": role.character_id,
            "character_name": role.name,
            "slide_count": len(slides),
            "slides": slides,
            "generation_mode": "fallback",
        }
