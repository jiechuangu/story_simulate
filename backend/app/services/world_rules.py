"""
世界规则执行器

为小说世界提供不依赖社交媒体平台的原生演化逻辑。
当前实现采用确定性启发式规则，后续可逐步替换为 LLM + 规则混合驱动。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List

from ..utils.llm_client import LLMClient


@dataclass
class CharacterDecision:
    character_id: str
    title: str
    description: str
    location: str
    goal: str
    mood: str
    related_character_ids: List[str]
    metadata: Dict[str, object]


@dataclass
class DialogueOutcome:
    character_response: str
    emotional_shift: str
    revealed_fact: str
    relationship_note: str
    target_goal_update: str
    state_update_summary: str


class WorldRuleEngine:
    DEFAULT_LOCATIONS = [
        "Residence",
        "Garden",
        "Archive",
        "Market",
        "Hall",
        "Riverside",
        "Library",
        "Watchtower",
    ]

    GOAL_BY_PROFESSION = {
        "student": "collect rumors and personal impressions",
        "professor": "interpret hidden motives and evidence",
        "official": "stabilize the public order around the incident",
        "journalist": "track every new clue and witness statement",
        "media": "amplify or frame the latest turning point",
        "doctor": "observe physical and emotional changes in others",
        "lawyer": "assess risk, responsibility, and leverage",
    }

    def __init__(self):
        self._llm = None

    def simulate(self, state, delta_hours: int) -> None:
        steps = max(1, min(12, delta_hours if delta_hours <= 24 else max(1, delta_hours // 12)))
        hours_per_step = max(1, delta_hours // steps)

        for step_index in range(steps):
            simulated_at = datetime.fromisoformat(state.current_world_time) + timedelta(hours=hours_per_step)
            state.current_world_time = simulated_at.isoformat()
            state.elapsed_hours += hours_per_step

            active_characters = self._select_active_characters(state, step_index)
            for character in active_characters:
                decision = self._decide(character, state, step_index, simulated_at)
                self._apply_decision(character, state, decision, simulated_at)

    def _select_active_characters(self, state, step_index: int):
        characters = state.characters[:]
        characters.sort(key=lambda item: item.character_id)
        window = min(max(3, len(characters) // 2), len(characters))
        start = (step_index * window) % max(len(characters), 1)
        selected = []
        for offset in range(window):
            if not characters:
                break
            selected.append(characters[(start + offset) % len(characters)])
        return selected

    def _decide(self, character, state, step_index: int, simulated_at: datetime) -> CharacterDecision:
        command_facts = []
        preference_facts = []
        appearance_facts = []
        for fact in state.facts:
            if fact.subject != character.character_id:
                continue
            tags = set(fact.tags or [])
            if "command" in tags:
                command_facts.append(fact)
            elif "appearance" in tags:
                appearance_facts.append(fact)
            else:
                preference_facts.append(fact)

        related_ids = []
        if state.player_character_id and state.player_character_id != character.character_id:
            related_ids.append(state.player_character_id)

        profession = (character.profession or character.source_entity_type or "").lower()
        base_goal = "observe the shifting state of the world"
        for key, goal in self.GOAL_BY_PROFESSION.items():
            if key in profession:
                base_goal = goal
                break

        if command_facts:
            fact = command_facts[step_index % len(command_facts)]
            goal = f"execute instruction: {fact.object_value}"
            mood = "committed"
            title = "Carry Out An Instruction"
            description = f"{character.name} adjusts their behavior to comply with the injected directive: {fact.object_value}."
        elif preference_facts:
            fact = preference_facts[step_index % len(preference_facts)]
            goal = f"act under the influence of '{fact.object_value}'"
            mood = "self-aware"
            title = "React To A Personal Fact"
            description = (
                f"{character.name} makes a choice shaped by the injected fact "
                f"'{fact.natural_language or fact.object_value}', which subtly alters the surrounding situation."
            )
        else:
            topics = ", ".join(character.interested_topics[:2]) if character.interested_topics else "the latest tension"
            goal = base_goal
            mood = "alert" if step_index % 2 == 0 else "reflective"
            title = "Pursue A World Goal"
            description = f"{character.name} focuses on {base_goal}, paying close attention to {topics}."

        if appearance_facts:
            description += f" Their visible image is reinforced by details such as {appearance_facts[0].object_value}."

        location_seed = abs(hash(f"{character.character_id}:{simulated_at.hour}:{step_index}"))
        location = self.DEFAULT_LOCATIONS[location_seed % len(self.DEFAULT_LOCATIONS)]

        return CharacterDecision(
            character_id=character.character_id,
            title=title,
            description=description,
            location=location,
            goal=goal,
            mood=mood,
            related_character_ids=related_ids,
            metadata={
                "hour": simulated_at.hour,
                "step_index": step_index,
                "topics": character.interested_topics[:3],
            },
        )

    def _apply_decision(self, character, state, decision: CharacterDecision, simulated_at: datetime) -> None:
        character.current_location = decision.location
        character.current_goal = decision.goal
        character.status_summary = decision.description
        character.last_active_at = simulated_at.isoformat()
        if decision.mood and decision.mood not in character.traits:
            character.traits = [decision.mood, *character.traits[:5]]

        event_id = f"event_rule_{len(state.timeline_events) + 1}"
        state.timeline_events.insert(
            0,
            state.timeline_events[0].__class__(
                event_id=event_id,
                event_type="world_rule",
                title=f"{character.name}: {decision.title}",
                description=decision.description,
                happened_at=datetime.now().isoformat(),
                related_character_ids=[character.character_id, *decision.related_character_ids],
                metadata={
                    "location": decision.location,
                    "goal": decision.goal,
                    "mood": decision.mood,
                    **decision.metadata,
                },
            ),
        )

    def handle_dialogue(self, state, speaker, target, message: str) -> DialogueOutcome:
        prompt_payload = {
            "world_name": state.world_name,
            "world_requirement": state.simulation_requirement,
            "speaker_name": speaker.name if speaker else "玩家",
            "speaker_goal": speaker.current_goal if speaker else "影响对话走向",
            "target_name": target.name,
            "target_profession": target.profession or target.source_entity_type,
            "target_goal": target.current_goal,
            "target_location": target.current_location,
            "target_summary": target.summary,
            "target_persona": target.persona[:1200],
            "target_traits": target.traits[:6],
            "appearance_notes": target.appearance_notes[:4],
            "message": message,
        }

        outcome = self._llm_dialogue(prompt_payload)
        if not outcome:
            outcome = self._fallback_dialogue(target, message)
        return outcome

    def _llm_dialogue(self, payload: Dict[str, object]) -> DialogueOutcome | None:
        try:
            if self._llm is None:
                self._llm = LLMClient()
            result = self._llm.chat_json(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一个文学世界模拟引擎。"
                            "你必须返回 JSON，包含键：character_response, emotional_shift, revealed_fact, "
                            "relationship_note, target_goal_update, state_update_summary。"
                            "回答要简洁、保持角色口吻，并让状态变化具备叙事意义。"
                            "输出语言使用中文。"
                        ),
                    },
                    {"role": "user", "content": str(payload)},
                ],
                temperature=0.7,
                max_tokens=800,
            )
            return DialogueOutcome(
                character_response=result.get("character_response", ""),
                emotional_shift=result.get("emotional_shift", "curious"),
                revealed_fact=result.get("revealed_fact", ""),
                relationship_note=result.get("relationship_note", ""),
                target_goal_update=result.get("target_goal_update", ""),
                state_update_summary=result.get("state_update_summary", ""),
            )
        except Exception:
            return None

    def _fallback_dialogue(self, target, message: str) -> DialogueOutcome:
        lowered = message.lower()
        if "秘密" in message or "secret" in lowered:
            revealed = f"{target.name} 暗示自己知道的比之前透露的更多。"
        else:
            revealed = f"{target.name} 在这次交流后更明确地感知到了玩家意图。"
        return DialogueOutcome(
            character_response=f"{target.name} 谨慎回应：“{message[:24]}……我会记住这件事。”",
            emotional_shift="警惕" if "?" in message else "投入",
            revealed_fact=revealed,
            relationship_note=f"{target.name} 会更关注玩家后续的行动。",
            target_goal_update=f"重新评估这句话带来的影响：{message[:40]}",
            state_update_summary=f"这次对话改变了{target.name}的优先级，并在世界状态中留下了新的痕迹。",
        )
