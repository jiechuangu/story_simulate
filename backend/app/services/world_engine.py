"""
世界模拟引擎

在保留 Zep 图谱与既有 simulation bootstrap 的前提下，为小说世界交互提供：
1. 世界状态持久化
2. 角色占用/玩家扮演
3. 时间线推进
4. Fact 注入
5. 角色图像生成任务
"""

import json
import os
import re
import subprocess
import csv
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..config import Config
from ..models.project import ProjectManager
from ..utils.logger import get_logger
from .graph_store_factory import create_graph_store
from .simulation_manager import SimulationManager
from .world_rules import WorldRuleEngine

logger = get_logger("mirofish.world_engine")


def _now_iso() -> str:
    return datetime.now().isoformat()


def _slugify(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip())
    return safe.strip("-") or "item"


def _excerpt(text: str, max_len: int = 220) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _hours_from_unit(amount: int, unit: str) -> int:
    unit = (unit or "day").lower()
    mapping = {
        "hour": 1,
        "hours": 1,
        "day": 24,
        "days": 24,
        "week": 24 * 7,
        "weeks": 24 * 7,
        "month": 24 * 30,
        "months": 24 * 30,
        "year": 24 * 365,
        "years": 24 * 365,
    }
    if unit not in mapping:
        raise ValueError(f"不支持的时间单位: {unit}")
    return amount * mapping[unit]


@dataclass
class WorldFact:
    fact_id: str
    scope: str
    subject: str
    predicate: str
    object_value: str
    source: str = "user"
    natural_language: str = ""
    effective_time: str = "immediate"
    duration: Optional[str] = None
    priority: int = 5
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)


@dataclass
class ImageTask:
    task_id: str
    character_id: str
    model: str
    prompt: str
    negative_prompt: str = ""
    style: str = "character-portrait"
    status: str = "pending"
    output_path: Optional[str] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=_now_iso)
    completed_at: Optional[str] = None


@dataclass
class WorldCharacter:
    character_id: str
    name: str
    handle: str
    summary: str
    persona: str
    profession: str = ""
    source_entity_uuid: str = ""
    source_entity_type: str = ""
    interested_topics: List[str] = field(default_factory=list)
    traits: List[str] = field(default_factory=list)
    appearance_notes: List[str] = field(default_factory=list)
    injected_fact_ids: List[str] = field(default_factory=list)
    image_task_ids: List[str] = field(default_factory=list)
    current_location: str = "Unknown"
    current_goal: str = "Observe the world"
    status_summary: str = ""
    last_active_at: Optional[str] = None
    relationship_notes: Dict[str, str] = field(default_factory=dict)
    latest_image_task_id: Optional[str] = None
    claimed_by: Optional[str] = None
    is_player_controlled: bool = False


@dataclass
class TimelineEvent:
    event_id: str
    event_type: str
    title: str
    description: str
    happened_at: str
    related_character_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorldState:
    simulation_id: str
    project_id: str
    graph_id: str
    world_name: str
    simulation_requirement: str
    status: str = "ready"
    current_world_time: str = field(default_factory=_now_iso)
    elapsed_hours: int = 0
    time_scale_unit: str = "day"
    time_scale_amount: int = 1
    player_character_id: Optional[str] = None
    player_name: Optional[str] = None
    characters: List[WorldCharacter] = field(default_factory=list)
    facts: List[WorldFact] = field(default_factory=list)
    timeline_events: List[TimelineEvent] = field(default_factory=list)
    image_tasks: List[ImageTask] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "world_name": self.world_name,
            "simulation_requirement": self.simulation_requirement,
            "status": self.status,
            "current_world_time": self.current_world_time,
            "elapsed_hours": self.elapsed_hours,
            "time_scale_unit": self.time_scale_unit,
            "time_scale_amount": self.time_scale_amount,
            "player_character_id": self.player_character_id,
            "player_name": self.player_name,
            "characters": [asdict(item) for item in self.characters],
            "facts": [asdict(item) for item in self.facts],
            "timeline_events": [asdict(item) for item in self.timeline_events],
            "image_tasks": [asdict(item) for item in self.image_tasks],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorldState":
        return cls(
            simulation_id=data["simulation_id"],
            project_id=data["project_id"],
            graph_id=data["graph_id"],
            world_name=data["world_name"],
            simulation_requirement=data.get("simulation_requirement", ""),
            status=data.get("status", "ready"),
            current_world_time=data.get("current_world_time", _now_iso()),
            elapsed_hours=data.get("elapsed_hours", 0),
            time_scale_unit=data.get("time_scale_unit", "day"),
            time_scale_amount=data.get("time_scale_amount", 1),
            player_character_id=data.get("player_character_id"),
            player_name=data.get("player_name"),
            characters=[WorldCharacter(**item) for item in data.get("characters", [])],
            facts=[WorldFact(**item) for item in data.get("facts", [])],
            timeline_events=[TimelineEvent(**item) for item in data.get("timeline_events", [])],
            image_tasks=[ImageTask(**item) for item in data.get("image_tasks", [])],
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
        )


class WorldEngine:
    STORAGE_DIR = os.path.join(Config.UPLOAD_FOLDER, "worlds")
    PLAYABLE_ENTITY_TYPES = {"character", "person", "human"}
    NON_PLAYABLE_KEYWORDS = [
        "学院", "宗", "门", "殿", "塔", "森林", "酒店", "村", "帝国", "王国", "组织", "势力", "机构", "总部", "联盟",
        "academy", "sect", "clan", "hall", "temple", "forest", "village", "kingdom", "empire", "organization", "faction",
    ]

    def __init__(self):
        os.makedirs(self.STORAGE_DIR, exist_ok=True)
        self.simulation_manager = SimulationManager()
        self.rule_engine = WorldRuleEngine()
        self._graph_store = None

    def _world_dir(self, simulation_id: str) -> str:
        path = os.path.join(self.STORAGE_DIR, simulation_id)
        os.makedirs(path, exist_ok=True)
        os.makedirs(os.path.join(path, "images"), exist_ok=True)
        return path

    def _world_state_path(self, simulation_id: str) -> str:
        return os.path.join(self._world_dir(simulation_id), "world_state.json")

    def _normalize_entity_type(self, entity_type: str) -> str:
        value = (entity_type or "").strip().lower()
        aliases = {
            "people": "person",
            "人物": "character",
            "角色": "character",
            "persona": "character",
        }
        return aliases.get(value, value)

    def _infer_entity_type(self, name: str, profession: str, persona: str) -> str:
        name_text = (name or "").strip()

        for kw in self.NON_PLAYABLE_KEYWORDS:
            if kw in name_text:
                if kw in ["森林", "酒店", "村", "academy", "forest", "village"]:
                    return "Location"
                if kw in ["塔", "artifact"]:
                    return "Artifact"
                return "Faction"
        return "Character"

    def _is_playable_character(self, character: WorldCharacter) -> bool:
        entity_type = self._normalize_entity_type(character.source_entity_type)
        if entity_type:
            return entity_type in self.PLAYABLE_ENTITY_TYPES

        inferred = self._infer_entity_type(
            name=character.name,
            profession=character.profession,
            persona=character.persona,
        )
        return self._normalize_entity_type(inferred) in self.PLAYABLE_ENTITY_TYPES

    def _assert_playable_character(self, character: WorldCharacter, action: str) -> None:
        if not self._is_playable_character(character):
            raise ValueError(f"{action}仅支持 Character 实体，当前实体不支持: {character.name}")

    def _save(self, state: WorldState) -> None:
        state.updated_at = _now_iso()
        with open(self._world_state_path(state.simulation_id), "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)

    def get_world(self, simulation_id: str) -> Optional[WorldState]:
        path = self._world_state_path(simulation_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return WorldState.from_dict(json.load(f))

    def bootstrap_world(self, simulation_id: str, force_rebuild: bool = False) -> WorldState:
        existing = self.get_world(simulation_id)
        if existing and not force_rebuild:
            return existing

        simulation = self.simulation_manager.get_simulation(simulation_id)
        if not simulation:
            raise ValueError(f"模拟不存在: {simulation_id}")

        project = ProjectManager.get_project(simulation.project_id)
        if not project:
            raise ValueError(f"项目不存在: {simulation.project_id}")

        profiles = self._load_bootstrap_profiles(simulation_id)
        if not profiles:
            raise ValueError("未找到可用于初始化世界引擎的角色 profiles，请先完成环境搭建")
        graph_type_map = self._load_graph_entity_type_map(simulation.graph_id)

        characters: List[WorldCharacter] = []
        facts: List[WorldFact] = []

        for index, profile in enumerate(profiles):
            character_id = f"char_{index:03d}"
            bio = profile.get("bio", "")
            persona = profile.get("persona", "")
            summary = _excerpt(bio or persona, 180)
            appearance_notes = self._extract_appearance_notes(profile)
            if appearance_notes:
                fact_id = f"fact_boot_{index:03d}"
                facts.append(
                    WorldFact(
                        fact_id=fact_id,
                        scope="character",
                        subject=character_id,
                        predicate="appearance_hint",
                        object_value="; ".join(appearance_notes),
                        source="bootstrap",
                        natural_language=f"{profile.get('username') or profile.get('name') or character_id} 的外貌线索: {'; '.join(appearance_notes)}",
                        tags=["appearance", "bootstrap"],
                    )
                )
                injected = [fact_id]
            else:
                injected = []

            source_entity_type = self._resolve_profile_entity_type(profile, graph_type_map)
            characters.append(
                WorldCharacter(
                    character_id=character_id,
                    name=profile.get("username") or profile.get("name") or f"Character {index + 1}",
                    handle=profile.get("name") or profile.get("username") or f"character_{index + 1}",
                    summary=summary,
                    persona=persona,
                    profession=profile.get("profession", ""),
                    source_entity_uuid=profile.get("source_entity_uuid", ""),
                    source_entity_type=source_entity_type,
                    interested_topics=profile.get("interested_topics", []),
                    traits=self._extract_traits(profile),
                    appearance_notes=appearance_notes,
                    injected_fact_ids=injected,
                    current_location=self.DEFAULT_WORLD_LOCATION(index),
                    current_goal=self._infer_initial_goal(profile),
                    status_summary=summary,
                )
            )

        current_time = _now_iso()
        state = WorldState(
            simulation_id=simulation_id,
            project_id=simulation.project_id,
            graph_id=simulation.graph_id,
            world_name=project.name or f"World {simulation_id}",
            simulation_requirement=project.simulation_requirement or "",
            current_world_time=current_time,
            characters=characters,
            facts=facts,
            timeline_events=[
                TimelineEvent(
                    event_id="event_bootstrap",
                    event_type="bootstrap",
                    title="世界引擎初始化",
                    description="已基于现有图谱、角色人设与模拟配置生成初始世界状态。",
                    happened_at=current_time,
                    metadata={
                        "character_count": len(characters),
                        "fact_count": len(facts),
                    },
                )
            ],
        )
        self._save(state)
        return state

    def _load_graph_entity_type_map(self, graph_id: str) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        try:
            if self._graph_store is None:
                self._graph_store = create_graph_store()
            if not hasattr(self._graph_store, "get_graph_data"):
                return mapping
            graph_data = self._graph_store.get_graph_data(graph_id, include_inactive=True)
            for node in graph_data.get("nodes", []):
                name = (node.get("name") or "").strip()
                if not name:
                    continue
                labels = node.get("labels") or []
                entity_type = next((label for label in labels if label not in {"Entity", "Node"}), "")
                if not entity_type:
                    continue
                mapping[name.lower()] = entity_type
        except Exception as exc:
            logger.warning("加载图谱实体类型映射失败: graph=%s error=%s", graph_id, exc)
        return mapping

    def _resolve_profile_entity_type(self, profile: Dict[str, Any], graph_type_map: Dict[str, str]) -> str:
        profile_type = (profile.get("source_entity_type") or "").strip()
        if profile_type:
            return profile_type

        candidates = []
        for key in ("name", "username"):
            value = (profile.get(key) or "").strip()
            if value:
                candidates.append(value)
                candidates.append(re.sub(r"_\d+$", "", value))

        for candidate in candidates:
            mapped = graph_type_map.get(candidate.lower())
            if mapped:
                return mapped

        return self._infer_entity_type(
            name=profile.get("username") or profile.get("name") or "",
            profession=profile.get("profession", ""),
            persona=profile.get("persona", ""),
        )

    def claim_character(self, simulation_id: str, character_id: str, player_name: str) -> WorldState:
        state = self._require_world(simulation_id)
        found = None
        for character in state.characters:
            if character.character_id == character_id:
                character.claimed_by = player_name
                character.is_player_controlled = True
                found = character
            else:
                character.claimed_by = None
                character.is_player_controlled = False

        if not found:
            raise ValueError(f"角色不存在: {character_id}")
        self._assert_playable_character(found, "玩家扮演")

        state.player_character_id = character_id
        state.player_name = player_name
        state.timeline_events.insert(
            0,
            TimelineEvent(
                event_id=f"event_claim_{len(state.timeline_events)+1}",
                event_type="player_claim",
                title="玩家进入世界",
                description=f"{player_name} 已接管角色 {found.name}。",
                happened_at=_now_iso(),
                related_character_ids=[character_id],
            ),
        )
        self._save(state)
        return state

    def add_character(
        self,
        simulation_id: str,
        name: str,
        persona: str = "",
        summary: str = "",
        profession: str = "",
        current_location: str = "",
        current_goal: str = "",
        appearance_notes: Optional[List[str]] = None,
    ) -> WorldState:
        state = self._require_world(simulation_id)
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValueError("角色名称不能为空")

        used_ids = {item.character_id for item in state.characters}
        next_index = len(state.characters)
        while True:
            character_id = f"char_{next_index:03d}"
            if character_id not in used_ids:
                break
            next_index += 1

        fallback_summary = _excerpt(summary or persona or f"{clean_name} is a new character in this world.", 180)
        character = WorldCharacter(
            character_id=character_id,
            name=clean_name,
            handle=_slugify(clean_name),
            summary=fallback_summary,
            persona=persona or fallback_summary,
            profession=profession or "Character",
            source_entity_type="Character",
            interested_topics=[],
            traits=["custom"],
            appearance_notes=[x.strip() for x in (appearance_notes or []) if str(x).strip()][:6],
            injected_fact_ids=[],
            current_location=(current_location or self.DEFAULT_WORLD_LOCATION(next_index)).strip(),
            current_goal=(current_goal or "observe the shifting state of the world").strip(),
            status_summary=fallback_summary,
        )
        state.characters.append(character)

        state.timeline_events.insert(
            0,
            TimelineEvent(
                event_id=f"event_add_character_{len(state.timeline_events)+1}",
                event_type="character_added",
                title="新角色加入世界",
                description=f"{clean_name} 已加入世界并可被玩家扮演。",
                happened_at=_now_iso(),
                related_character_ids=[character.character_id],
                metadata={"character_id": character.character_id, "source": "user_created"},
            ),
        )

        self._save(state)
        return state

    def release_character(self, simulation_id: str) -> WorldState:
        state = self._require_world(simulation_id)
        if state.player_character_id:
            for character in state.characters:
                if character.character_id == state.player_character_id:
                    character.claimed_by = None
                    character.is_player_controlled = False
                    break

            state.timeline_events.insert(
                0,
                TimelineEvent(
                    event_id=f"event_release_{len(state.timeline_events)+1}",
                    event_type="player_release",
                    title="玩家离开角色",
                    description=f"{state.player_name or '玩家'} 已退出当前角色占用。",
                    happened_at=_now_iso(),
                    related_character_ids=[state.player_character_id],
                ),
            )

        state.player_character_id = None
        state.player_name = None
        self._save(state)
        return state

    def advance_time(
        self,
        simulation_id: str,
        amount: int,
        unit: str,
        narrative_instruction: str = "",
    ) -> WorldState:
        state = self._require_world(simulation_id)
        delta_hours = _hours_from_unit(amount, unit)
        state.time_scale_amount = amount
        state.time_scale_unit = unit
        self.rule_engine.simulate(state, delta_hours)
        state.timeline_events.insert(
            0,
            TimelineEvent(
                event_id=f"event_time_{len(state.timeline_events)+1}",
                event_type="time_advance",
                title="时间推进",
                description=narrative_instruction or f"世界规则执行器已推动时间前进 {amount} {unit}，并完成该时段内的角色演化。",
                happened_at=_now_iso(),
                metadata={
                    "amount": amount,
                    "unit": unit,
                    "elapsed_hours": state.elapsed_hours,
                    "world_time": state.current_world_time,
                },
            ),
        )
        self._save(state)
        return state

    def add_fact(
        self,
        simulation_id: str,
        scope: str,
        subject: str,
        predicate: str,
        object_value: str,
        natural_language: str = "",
        effective_time: str = "immediate",
        duration: Optional[str] = None,
        priority: int = 5,
        tags: Optional[List[str]] = None,
    ) -> WorldState:
        state = self._require_world(simulation_id)
        fact_id = f"fact_{len(state.facts)+1:04d}"
        fact = WorldFact(
            fact_id=fact_id,
            scope=scope,
            subject=subject,
            predicate=predicate,
            object_value=object_value,
            natural_language=natural_language,
            effective_time=effective_time,
            duration=duration,
            priority=priority,
            tags=tags or [],
        )
        state.facts.insert(0, fact)

        matched_subject = False
        for character in state.characters:
            if character.character_id == subject:
                matched_subject = True
                if scope == "character":
                    self._assert_playable_character(character, "Fact 注入")
                character.injected_fact_ids.insert(0, fact_id)
                if "appearance" in fact.tags or predicate in {"appearance", "appearance_hint", "wears", "looks_like"}:
                    character.appearance_notes.insert(0, object_value)
                break
        if scope == "character" and not matched_subject:
            raise ValueError(f"角色不存在或不可注入: {subject}")

        state.timeline_events.insert(
            0,
            TimelineEvent(
                event_id=f"event_fact_{len(state.timeline_events)+1}",
                event_type="fact_injection",
                title="新世界事实注入",
                description=natural_language or f"{subject} {predicate} {object_value}",
                happened_at=_now_iso(),
                related_character_ids=[subject] if scope == "character" else [],
                metadata={"fact_id": fact_id, "scope": scope},
            ),
        )
        self._save(state)
        return state

    def create_image_task(
        self,
        simulation_id: str,
        character_id: str,
        model: Optional[str] = None,
        style: str = "character-portrait",
        prompt_override: str = "",
        negative_prompt: str = "",
        auto_generate: bool = True,
    ) -> ImageTask:
        state = self._require_world(simulation_id)
        character = next((item for item in state.characters if item.character_id == character_id), None)
        if not character:
            raise ValueError(f"角色不存在: {character_id}")
        self._assert_playable_character(character, "生成人物形象")

        task_id = f"img_{len(state.image_tasks)+1:04d}"
        prompt = prompt_override or self._build_image_prompt(state, character)
        task = ImageTask(
            task_id=task_id,
            character_id=character_id,
            model=model or os.environ.get("OLLAMA_IMAGE_MODEL", "x/flux2-klein:4b-fp8"),
            prompt=prompt,
            negative_prompt=negative_prompt or "blurry, low detail, extra limbs, duplicate face, distorted anatomy, text watermark",
            style=style,
            status="queued" if auto_generate else "pending",
        )
        state.image_tasks.insert(0, task)
        character.image_task_ids.insert(0, task_id)
        character.latest_image_task_id = task_id
        self._save(state)

        if auto_generate:
            self._run_image_task(state, task)
            self._save(state)

        return task

    def list_image_tasks(self, simulation_id: str) -> List[Dict[str, Any]]:
        state = self._require_world(simulation_id)
        return [asdict(task) for task in state.image_tasks]

    def get_image_task(self, simulation_id: str, task_id: str) -> Optional[ImageTask]:
        state = self._require_world(simulation_id)
        return next((task for task in state.image_tasks if task.task_id == task_id), None)

    def process_dialogue(
        self,
        simulation_id: str,
        target_character_id: str,
        message: str,
    ) -> Dict[str, Any]:
        state = self._require_world(simulation_id)
        target = next((item for item in state.characters if item.character_id == target_character_id), None)
        if not target:
            raise ValueError(f"角色不存在: {target_character_id}")
        self._assert_playable_character(target, "人物对话")

        speaker = None
        if state.player_character_id:
            speaker = next((item for item in state.characters if item.character_id == state.player_character_id), None)
            if speaker:
                self._assert_playable_character(speaker, "玩家人物对话")

        outcome = self.rule_engine.handle_dialogue(state, speaker, target, message)
        target.status_summary = outcome.state_update_summary or outcome.character_response
        target.current_goal = outcome.target_goal_update or target.current_goal
        target.last_active_at = _now_iso()

        relation_key = speaker.character_id if speaker else "player"
        target.relationship_notes[relation_key] = outcome.relationship_note or outcome.emotional_shift
        if speaker:
            speaker.relationship_notes[target.character_id] = outcome.relationship_note or outcome.emotional_shift

        dialogue_event_id = f"event_dialogue_{len(state.timeline_events)+1}"
        state.timeline_events.insert(
            0,
            TimelineEvent(
                event_id=dialogue_event_id,
                event_type="dialogue",
                title=f"{target.name} held a conversation",
                description=outcome.state_update_summary or outcome.character_response,
                happened_at=_now_iso(),
                related_character_ids=[target.character_id] + ([speaker.character_id] if speaker else []),
                metadata={
                    "player_message": message,
                    "character_response": outcome.character_response,
                    "relationship_note": outcome.relationship_note,
                    "emotional_shift": outcome.emotional_shift,
                },
            ),
        )

        if outcome.revealed_fact:
            fact_subject = target.character_id
            fact_id = f"fact_{len(state.facts)+1:04d}"
            state.facts.insert(
                0,
                WorldFact(
                    fact_id=fact_id,
                    scope="character",
                    subject=fact_subject,
                    predicate="revealed_in_dialogue",
                    object_value=outcome.revealed_fact,
                    source="dialogue",
                    natural_language=outcome.revealed_fact,
                    tags=["dialogue", "memory"],
                ),
            )
            target.injected_fact_ids.insert(0, fact_id)

        self._save(state)
        return {
            "world_state": state.to_dict(),
            "dialogue": {
                "target_character_id": target.character_id,
                "target_name": target.name,
                "player_message": message,
                "character_response": outcome.character_response,
                "relationship_note": outcome.relationship_note,
                "revealed_fact": outcome.revealed_fact,
                "target_goal": target.current_goal,
            },
        }

    def _run_image_task(self, state: WorldState, task: ImageTask) -> None:
        images_dir = os.path.join(self._world_dir(state.simulation_id), "images", task.task_id)
        os.makedirs(images_dir, exist_ok=True)
        before = set(os.listdir(images_dir))
        task.status = "running"

        try:
            command = ["ollama", "run", task.model, task.prompt]
            logger.info("执行角色图像生成任务: %s", " ".join(command[:3]))
            result = subprocess.run(
                command,
                cwd=images_dir,
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
            )
            if result.returncode != 0:
                task.status = "failed"
                task.error = result.stderr.strip() or result.stdout.strip() or "ollama run 执行失败"
                return

            created = [
                os.path.join(images_dir, item)
                for item in os.listdir(images_dir)
                if item not in before and item.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
            ]
            if created:
                created.sort(key=os.path.getmtime, reverse=True)
                task.output_path = created[0]
                task.status = "completed"
                task.completed_at = _now_iso()
            else:
                task.status = "failed"
                task.error = "未检测到生成的图片文件，请确认本地 Ollama 图像模型是否可用"
        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)

    def _build_image_prompt(self, state: WorldState, character: WorldCharacter) -> str:
        appearance_facts = []
        for fact in state.facts:
            if fact.subject == character.character_id and (
                "appearance" in fact.tags
                or fact.predicate in {"appearance", "appearance_hint", "wears", "looks_like"}
            ):
                appearance_facts.append(fact.object_value)

        appearance_lines = appearance_facts or character.appearance_notes
        appearance_text = "; ".join(dict.fromkeys([item for item in appearance_lines if item])) or "appearance inferred from literary persona"
        trait_text = ", ".join(character.traits[:4]) if character.traits else "distinctive literary character"
        topic_text = ", ".join(character.interested_topics[:4]) if character.interested_topics else "story-driven world"

        return (
            f"Character portrait of {character.name}, {character.profession or 'story character'}, "
            f"{trait_text}. Appearance details: {appearance_text}. "
            f"World premise: {state.simulation_requirement or state.world_name}. "
            f"Interests or themes: {topic_text}. "
            f"Current location: {character.current_location}. Current goal: {character.current_goal}. "
            "Cinematic half-body illustration, highly detailed face, consistent costume design, clean background, no text, no watermark."
        )

    def _extract_traits(self, profile: Dict[str, Any]) -> List[str]:
        traits = []
        for key in ("mbti", "profession", "gender", "country"):
            value = profile.get(key)
            if value:
                traits.append(str(value))
        return traits

    def _extract_appearance_notes(self, profile: Dict[str, Any]) -> List[str]:
        text = " ".join(
            [
                str(profile.get("bio", "")),
                str(profile.get("persona", "")),
            ]
        )
        lines = []
        patterns = [
            r"(wearing [^.,;]+)",
            r"(dressed in [^.,;]+)",
            r"(with [^.,;]*(?:hair|eyes|robe|dress|coat|armor)[^.,;]*)",
            r"(身穿[^。；，]+)",
            r"(穿着[^。；，]+)",
            r"(留着[^。；，]+)",
            r"(有着[^。；，]+(?:头发|眼睛|长袍|衣裙|盔甲)[^。；，]*)",
        ]
        for pattern in patterns:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                cleaned = _excerpt(match, 100)
                if cleaned and cleaned not in lines:
                    lines.append(cleaned)
                if len(lines) >= 4:
                    return lines
        return lines

    def _require_world(self, simulation_id: str) -> WorldState:
        state = self.get_world(simulation_id)
        if not state:
            raise ValueError("世界状态不存在，请先初始化世界引擎")
        return state

    def _infer_initial_goal(self, profile: Dict[str, Any]) -> str:
        profession = (profile.get("profession") or "").lower()
        if "student" in profession:
            return "Understand the undercurrents around them"
        if "official" in profession:
            return "Maintain order and control outcomes"
        if "journalist" in profession or "media" in profession:
            return "Find the next decisive clue"
        return "Observe the world and respond to changes"

    @staticmethod
    def DEFAULT_WORLD_LOCATION(index: int) -> str:
        locations = [
            "Residence",
            "Garden",
            "Archive",
            "Hall",
            "Riverside",
            "Market",
        ]
        return locations[index % len(locations)]

    def _load_bootstrap_profiles(self, simulation_id: str) -> List[Dict[str, Any]]:
        profiles = self.simulation_manager.get_profiles(simulation_id, "reddit")
        if profiles:
            return profiles

        sim_dir = self.simulation_manager._get_simulation_dir(simulation_id)
        twitter_csv = os.path.join(sim_dir, "twitter_profiles.csv")
        if not os.path.exists(twitter_csv):
            return []

        with open(twitter_csv, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        normalized = []
        for row in rows:
            normalized.append(
                {
                    "username": row.get("username") or row.get("user_name") or row.get("name"),
                    "name": row.get("name") or row.get("username"),
                    "bio": row.get("bio", ""),
                    "persona": row.get("persona", row.get("bio", "")),
                    "profession": row.get("profession", ""),
                    "interested_topics": [],
                }
            )
        return normalized
