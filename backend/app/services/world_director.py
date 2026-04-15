"""
后端剧情导演器

职责：
1. 从世界状态中提取角色、事件、关系、可达对话目标
2. 从图谱读取与当前角色相关的事实
3. 生成 Step6 所需的剧情节点与建议动作（优先 LLM，失败则回退规则）
"""

from __future__ import annotations

import concurrent.futures
from typing import Any, Dict, List, Optional, Tuple

from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .graph_store_factory import create_graph_store
from .world_engine import WorldEngine

logger = get_logger("mirofish.world_director")

AGENT_TYPES = {"character", "person", "human"}
ALIASES = {"people": "person", "人物": "character", "角色": "character"}
AGENTIC_VERBS = ["交易", "谈判", "对话", "询问", "说服", "会面", "合作", "命令", "拜访", "结盟", "冲突", "交涉"]


def _clip(text: str, limit: int = 220) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


class WorldNarrativeDirector:
    LLM_TIMEOUT_SECONDS = 25

    def __init__(self):
        self._engine = WorldEngine()
        self._llm: Optional[LLMClient] = None

    def build_node(
        self,
        simulation_id: str,
        character_id: str,
        target_character_id: str = "",
        narrative_step: int = 0,
    ) -> Dict[str, Any]:
        state = self._engine.get_world(simulation_id)
        if not state:
            raise ValueError(f"世界状态不存在: {simulation_id}")
        if not character_id:
            raise ValueError("缺少 character_id")

        role = next((c for c in state.characters if c.character_id == character_id), None)
        if not role:
            raise ValueError(f"角色不存在: {character_id}")
        if not self._is_agent(role):
            raise ValueError(f"当前实体不是可扮演角色: {role.name}")

        entity_registry = self._build_entity_registry(state)
        entity_map = {item["name"]: item for item in entity_registry}
        targets = self._rank_reachable_targets(state, role)
        resolved_target = self._pick_target(targets, target_character_id)
        recent_events = (state.timeline_events or [])[:6]
        graph_facts = self._load_graph_facts(
            state.graph_id,
            role.name,
            resolved_target["name"] if resolved_target else "",
            entity_map,
        )
        objectives = self._fallback_objectives(role, recent_events)

        prompt_payload = {
            "world_name": state.world_name,
            "world_requirement": _clip(state.simulation_requirement, 400),
            "world_time": state.current_world_time,
            "elapsed_hours": state.elapsed_hours,
            "narrative_step": max(0, int(narrative_step)),
            "role": {
                "id": role.character_id,
                "name": role.name,
                "entity_type": role.source_entity_type or "Character",
                "description": _clip(role.summary or role.persona, 180),
                "location": role.current_location,
                "goal": _clip(role.current_goal, 200),
                "status_summary": _clip(role.status_summary, 220),
                "traits": (role.traits or [])[:6],
                "topics": (role.interested_topics or [])[:5],
            },
            "entity_registry": entity_registry[:80],
            "objectives": objectives[:4],
            "targets": [
                {
                    "id": item["character_id"],
                    "name": item["name"],
                    "entity_type": item.get("source_entity_type") or "Character",
                    "description": _clip(item.get("description", ""), 160),
                    "location": item["current_location"],
                    "goal": _clip(item.get("current_goal", ""), 120),
                    "reason": item["reason"],
                }
                for item in targets[:8]
            ],
            "selected_target_id": resolved_target["character_id"] if resolved_target else "",
            "recent_events": [
                {
                    "event_type": event.event_type,
                    "title": _clip(event.title, 120),
                    "description": _clip(event.description, 180),
                    "related_character_ids": (event.related_character_ids or [])[:6],
                }
                for event in recent_events
            ],
            "graph_facts": graph_facts[:12],
            "constraints": {
                "agent_types": ["Character", "Person", "Human"],
                "non_agent_entities_can_only_be_clues": True,
                "forbid_non_agent_as_action_subject": True,
                "must_respect_entity_registry": True,
            },
        }

        generated = self._llm_generate(prompt_payload)
        if not generated:
            generated = self._fallback_node(role, resolved_target, recent_events, narrative_step)

        options = self._normalize_options(generated.get("node_options") or [], targets, resolved_target)
        objectives = self._normalize_objectives(generated.get("objectives") or [], role, recent_events)
        suggested = self._normalize_suggested_moves(generated.get("suggested_moves") or [])
        suggested = self._sanitize_suggested_moves(suggested, state, role, resolved_target, recent_events)

        if not suggested:
            suggested = self._fallback_suggested_moves(role, resolved_target, recent_events)
        if not options:
            options = self._fallback_options(role, resolved_target)
        if not objectives:
            objectives = self._fallback_objectives(role, recent_events)

        return {
            "narrative_step": max(0, int(narrative_step)) + 1,
            "node_title": _clip(generated.get("node_title") or f"叙事节点 {max(0, int(narrative_step)) + 1}", 80),
            "node_text": _clip(generated.get("node_text") or "世界正在等待你的下一步行动。", 360),
            "objectives": objectives[:4],
            "node_options": options[:4],
            "suggested_moves": suggested[:3],
            "dialogue_targets": targets[:12],
            "basis": {
                "role_id": role.character_id,
                "role_name": role.name,
                "current_location": role.current_location,
                "event_count": len(recent_events),
                "graph_fact_count": len(graph_facts),
                "events_used": [event.title for event in recent_events[:4]],
                "graph_facts_used": graph_facts[:5],
            },
        }

    def _pick_target(self, targets: List[Dict[str, Any]], target_character_id: str) -> Optional[Dict[str, Any]]:
        if not targets:
            return None
        if target_character_id:
            for item in targets:
                if item["character_id"] == target_character_id:
                    return item
        return targets[0]

    def _rank_reachable_targets(self, state, role) -> List[Dict[str, Any]]:
        related_from_plot = set()
        for event in (state.timeline_events or [])[:8]:
            for cid in event.related_character_ids or []:
                if cid and cid != role.character_id:
                    related_from_plot.add(cid)

        relation_keys = set((role.relationship_notes or {}).keys())
        role_location = (role.current_location or "").strip().lower()

        ranked: List[Tuple[int, Dict[str, Any]]] = []
        for candidate in state.characters:
            if candidate.character_id == role.character_id:
                continue
            if not self._is_agent(candidate):
                continue
            score = 0
            reasons: List[str] = []
            candidate_location = (candidate.current_location or "").strip().lower()
            if role_location and candidate_location and role_location == candidate_location:
                score += 3
                reasons.append("same_location")
            if candidate.character_id in related_from_plot:
                score += 2
                reasons.append("recent_plot")
            if candidate.character_id in relation_keys:
                score += 1
                reasons.append("known_relation")
            if score <= 0:
                continue
            ranked.append(
                (
                    score,
                    {
                        "character_id": candidate.character_id,
                        "name": candidate.name,
                        "current_location": candidate.current_location,
                        "current_goal": candidate.current_goal,
                        "source_entity_type": candidate.source_entity_type,
                        "description": candidate.summary or candidate.persona or "",
                        "reason": ",".join(reasons),
                        "score": score,
                    },
                )
            )

        if not ranked:
            fallback = [
                {
                    "character_id": c.character_id,
                    "name": c.name,
                    "current_location": c.current_location,
                    "current_goal": c.current_goal,
                    "source_entity_type": c.source_entity_type,
                    "description": c.summary or c.persona or "",
                    "reason": "fallback_any",
                    "score": 0,
                }
                for c in state.characters
                if c.character_id != role.character_id and self._is_agent(c)
            ]
            return fallback[:8]

        ranked.sort(key=lambda item: (-item[0], item[1]["name"]))
        return [item[1] for item in ranked]

    def _load_graph_facts(
        self,
        graph_id: str,
        role_name: str,
        target_name: str,
        entity_map: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[str]:
        facts: List[str] = []
        try:
            store = create_graph_store()
            for query in [role_name, target_name]:
                if not query:
                    continue
                partial = store.search_facts(graph_id=graph_id, query=query, limit=8)
                for fact in partial:
                    stripped = _clip(str(fact), 180)
                    if entity_map:
                        stripped = self._annotate_fact(stripped, entity_map)
                    if stripped and stripped not in facts:
                        facts.append(stripped)
                    if len(facts) >= 12:
                        return facts
        except Exception as exc:
            logger.warning("剧情导演读取图谱事实失败: %s", exc)
        return facts

    def _llm_generate(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            if self._llm is None:
                self._llm = LLMClient()

            def _run() -> Dict[str, Any]:
                return self._llm.chat_json(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "你是一个互动小说世界的后端剧情导演器。"
                                "你必须只返回严格 JSON，不要输出解释文本。"
                                "JSON 必须包含键：node_title, node_text, objectives, suggested_moves, node_options。"
                                "objectives：2-4 条“当前阶段玩家目标”。"
                                "suggested_moves：1-3 条简洁、可执行、以玩家视角表达的行动建议。"
                                "node_options：2-4 个对象，每个对象包含键：key, label, type, prompt, target_name, hours。"
                                "type 只能是 prompt 或 advance。"
                                "当 type=prompt 时，必须提供 prompt，可选 target_name。"
                                "当 type=advance 时，必须提供 hours，范围 6-72 的整数。"
                                "你会收到 entity_registry（实体清单，含 type/description/can_autonomous_action）。"
                                "你必须基于该清单做推演，不能无视实体类型。"
                                "硬约束：只有 Character/Person/Human 能执行自主行为。"
                                "Artifact/Location/Faction/Powersystem 等非生命实体只能作为线索、地点、规则或物件，不能被写成会交易/对话/决策的主体。"
                                "整体风格必须使用中文，符合当前世界设定与近期事件。"
                            ),
                        },
                        {"role": "user", "content": str(payload)},
                    ],
                    temperature=0.55,
                    max_tokens=900,
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
            logger.warning("剧情导演 LLM 超时(%ss)，回退规则", self.LLM_TIMEOUT_SECONDS)
            return None
        except Exception as exc:
            logger.warning("剧情导演 LLM 生成失败，将回退规则: %s", exc)
            return None

    def _normalize_suggested_moves(self, moves: List[Any]) -> List[str]:
        out: List[str] = []
        for item in moves or []:
            value = _clip(str(item), 120).strip()
            if value and value not in out:
                out.append(value)
            if len(out) >= 3:
                break
        return out

    def _normalize_objectives(self, objectives: List[Any], role, recent_events) -> List[str]:
        out: List[str] = []
        for item in objectives or []:
            value = _clip(str(item), 140).strip()
            if value and value not in out:
                out.append(value)
            if len(out) >= 4:
                break
        if out:
            return out
        return self._fallback_objectives(role, recent_events)

    def _normalize_options(
        self,
        options: List[Any],
        targets: List[Dict[str, Any]],
        resolved_target: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        by_name = {item["name"]: item for item in targets}
        by_lower = {item["name"].lower(): item for item in targets}
        out: List[Dict[str, Any]] = []
        for idx, raw in enumerate(options or []):
            if not isinstance(raw, dict):
                continue
            option_type = str(raw.get("type") or "prompt").strip().lower()
            if option_type not in {"prompt", "advance"}:
                option_type = "prompt"
            label = _clip(str(raw.get("label") or f"Option {idx + 1}"), 48)
            key = _clip(str(raw.get("key") or f"opt_{idx + 1}"), 40)
            option: Dict[str, Any] = {"key": key, "label": label, "type": option_type}
            if option_type == "advance":
                hours = raw.get("hours", 12)
                try:
                    hours = int(hours)
                except Exception:
                    hours = 12
                option["hours"] = max(6, min(72, hours))
            else:
                prompt = _clip(str(raw.get("prompt") or label), 220)
                target_name = str(raw.get("target_name") or "").strip()
                target = None
                if target_name:
                    target = by_name.get(target_name) or by_lower.get(target_name.lower())
                if not target:
                    target = resolved_target
                if target:
                    option["target_id"] = target["character_id"]
                option["prompt"] = prompt
            out.append(option)
            if len(out) >= 4:
                break
        return out

    def _fallback_suggested_moves(self, role, target: Optional[Dict[str, Any]], recent_events) -> List[str]:
        latest = recent_events[0].title if recent_events else "最近的局势变化"
        talk = target["name"] if target else "附近的角色"
        return [
            f"向{talk}追问“{latest}”背后的真实情况。",
            f"推进你的主目标：{role.current_goal or '稳定当前局势'}。",
            f"在{role.current_location or '你所在的位置'}重新评估风险与机会。",
        ]

    def _fallback_objectives(self, role, recent_events) -> List[str]:
        latest = recent_events[0].title if recent_events else "最近局势"
        objectives = [
            f"围绕“{latest}”确认关键因果与风险。",
            f"维持并推进当前核心目标：{role.current_goal or '观察局势'}。",
            f"基于你在{role.current_location or '当前位置'}的处境，制定下一轮行动。",
        ]
        topics = (role.interested_topics or [])[:2]
        if topics:
            objectives.append(f"补足与“{' / '.join(topics)}”相关的情报缺口。")
        return objectives[:4]

    def _normalize_entity_type(self, raw: str) -> str:
        value = (raw or "").strip().lower()
        return ALIASES.get(value, value)

    def _is_agent(self, character) -> bool:
        return self._normalize_entity_type(getattr(character, "source_entity_type", "")) in AGENT_TYPES

    def _build_entity_registry(self, state) -> List[Dict[str, Any]]:
        registry: List[Dict[str, Any]] = []
        for item in state.characters:
            raw_type = item.source_entity_type or ""
            normalized_type = self._normalize_entity_type(raw_type)
            can_act = normalized_type in AGENT_TYPES
            registry.append(
                {
                    "id": item.character_id,
                    "name": item.name,
                    "entity_type": raw_type or "Unknown",
                    "normalized_type": normalized_type or "unknown",
                    "description": _clip(item.summary or item.persona or "", 180),
                    "can_autonomous_action": can_act,
                    "location": item.current_location,
                }
            )
        return registry

    def _annotate_fact(self, fact: str, entity_map: Dict[str, Dict[str, Any]]) -> str:
        matched: List[str] = []
        for name, meta in entity_map.items():
            if not name:
                continue
            if name in fact:
                tag = meta.get("entity_type") or meta.get("normalized_type") or "Unknown"
                marker = "可行动" if meta.get("can_autonomous_action") else "非行动主体"
                matched.append(f"{name}:{tag}/{marker}")
                if len(matched) >= 3:
                    break
        if not matched:
            return fact
        return _clip(f"{fact}（实体注释：{'；'.join(matched)}）", 220)

    def _sanitize_suggested_moves(
        self,
        moves: List[str],
        state,
        role,
        resolved_target: Optional[Dict[str, Any]],
        recent_events,
    ) -> List[str]:
        non_agent_names = set()
        for c in state.characters:
            if self._is_agent(c):
                continue
            name = (c.name or "").strip()
            if not name:
                continue
            non_agent_names.add(name)
            base = name.split("_")[0].strip()
            if base:
                non_agent_names.add(base)

        safe: List[str] = []
        for move in moves:
            text = move.strip()
            if not text:
                continue
            violated_name = None
            for name in non_agent_names:
                if name and name in text and any(v in text for v in AGENTIC_VERBS):
                    violated_name = name
                    break
            if violated_name:
                latest = recent_events[0].title if recent_events else "当前局势"
                target_name = resolved_target["name"] if resolved_target else role.name
                text = (
                    f"把“{violated_name}”视为线索，向{target_name}核实它与“{latest}”的关联，"
                    "不要把该实体当作会自主行动的主体。"
                )
            clipped = _clip(text, 140)
            if clipped not in safe:
                safe.append(clipped)
            if len(safe) >= 3:
                break
        return safe

    def _fallback_options(self, role, target: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        options: List[Dict[str, Any]] = []
        if target:
            options.append(
                {
                    "key": f"talk_{target['character_id']}",
                    "label": f"询问{target['name']}",
                    "type": "prompt",
                    "target_id": target["character_id"],
                    "prompt": "我需要你对当前局势的判断。我们下一步该怎么做？",
                }
            )
        options.append(
            {
                "key": "wait_12h",
                "label": "观察12小时",
                "type": "advance",
                "hours": 12,
            }
        )
        options.append(
            {
                "key": "push_goal",
                "label": "推进主目标",
                "type": "prompt",
                "target_id": target["character_id"] if target else "",
                "prompt": f"我们需要果断推进这个目标：{role.current_goal or '继续向前'}。",
            }
        )
        return options

    def _fallback_node(self, role, target: Optional[Dict[str, Any]], recent_events, narrative_step: int) -> Dict[str, Any]:
        latest = recent_events[0] if recent_events else None
        target_name = target["name"] if target else "附近的角色"
        event_line = (
            f'最新转折点是“{latest.title}”。'
            if latest else
            "目前还没有记录到明确的剧情转折点。"
        )
        return {
            "node_title": f"叙事节点 {max(0, int(narrative_step)) + 1}",
            "node_text": (
                f"{role.name}目前位于{role.current_location}，目标是{role.current_goal}。"
                f"{event_line} 你可以与{target_name}交涉，也可以先让时间推进。"
            ),
            "objectives": self._fallback_objectives(role, recent_events),
            "node_options": self._fallback_options(role, target),
            "suggested_moves": self._fallback_suggested_moves(role, target, recent_events),
        }
