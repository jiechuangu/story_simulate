"""
故事领域模型。

WorldState 是唯一的事实来源：角色状态、每个角色各自知道的事实、关系、时间线都在这里。
章节正文只是对时间线里已发生事件的叙述。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def short_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class Character(BaseModel):
    id: str
    name: str
    aliases: List[str] = Field(default_factory=list)
    role: str = ""                  # 在故事中的位置：主角 / 配角 / 对手 ...
    description: str = ""           # 外貌、身份等公开可见信息
    personality: str = ""
    voice: str = ""                 # 说话方式
    goal: str = ""                  # 当前目标（会随剧情变化）
    location: str = ""
    mood: str = ""
    status: str = ""                # 处境：受伤、被软禁……
    active: bool = True             # 死亡 / 离场后为 False
    introduced_in: int = 0          # 0 表示蓝图人物，否则为登场章节号
    relationships: Dict[str, str] = Field(default_factory=dict)  # 对方角色 id -> 此角色眼中的关系


class Fact(BaseModel):
    id: str
    content: str
    known_by: List[str] = Field(default_factory=list)  # 角色 id；public=True 时忽略
    public: bool = False
    chapter_no: int = 0


class Event(BaseModel):
    id: str
    chapter_no: int
    scene_no: int
    location: str = ""
    actor: str = ""                 # 角色 id；"world" 表示环境 / 外部事件
    kind: str = "action"            # speech / action / world
    content: str = ""
    witnesses: List[str] = Field(default_factory=list)


class WorldState(BaseModel):
    time_label: str = ""
    setting: str = ""
    rules: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    characters: List[Character] = Field(default_factory=list)
    facts: List[Fact] = Field(default_factory=list)
    timeline: List[Event] = Field(default_factory=list)
    open_threads: List[str] = Field(default_factory=list)

    # ---- 查询 ----
    def char(self, ref: str) -> Optional[Character]:
        if not ref:
            return None
        key = ref.strip().lower()
        for c in self.characters:
            if c.id == ref or c.name.lower() == key or key in (a.lower() for a in c.aliases):
                return c
        return None

    def char_name(self, cid: str) -> str:
        if cid == "world":
            return "（环境）"
        c = self.char(cid)
        return c.name if c else cid

    def resolve_ids(self, refs) -> List[str]:
        if isinstance(refs, str):
            refs = [r for r in refs.replace("、", ",").split(",")]
        out: List[str] = []
        for r in refs or []:
            c = self.char(str(r))
            if c and c.id not in out:
                out.append(c.id)
        return out

    def facts_known_by(self, cid: str) -> List[Fact]:
        return [f for f in self.facts if f.public or cid in f.known_by]

    def events_witnessed_by(self, cid: str) -> List[Event]:
        return [e for e in self.timeline if cid in e.witnesses or e.actor == cid]


class Blueprint(BaseModel):
    title: str = ""
    premise: str = ""
    genre: str = ""
    style: str = ""
    setting: str = ""
    core_conflict: str = ""
    ending_direction: str = ""
    opening_situation: str = ""
    protagonist: str = ""
    summary: str = ""
    selling_points: List[str] = Field(default_factory=list)
    reader_promises: List[str] = Field(default_factory=list)
    characters: List[dict] = Field(default_factory=list)
    relationships: List[dict] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    rules: List[str] = Field(default_factory=list)
    opening_facts: List[dict] = Field(default_factory=list)


class Topic(BaseModel):
    id: str = Field(default_factory=lambda: short_id("topic"))
    title: str
    summary: str = ""
    focus_characters: List[str] = Field(default_factory=list)
    custom: bool = False


class ScenePlan(BaseModel):
    location: str = ""
    present: List[str] = Field(default_factory=list)   # 角色 id
    situation: str = ""
    world_event: str = ""


class Chapter(BaseModel):
    no: int
    title: str = ""
    topic: Optional[Topic] = None
    time_label: str = ""
    pov: str = ""
    style_id: str = ""
    pacing: str = ""
    introduced: List[str] = Field(default_factory=list)  # 本章新登场人物 id
    scenes: List[ScenePlan] = Field(default_factory=list)
    events: List[Event] = Field(default_factory=list)
    consistency_notes: List[str] = Field(default_factory=list)
    draft: str = ""
    content: str = ""
    summary: str = ""
    # 回退 / 重写用的快照
    world_before: Optional[WorldState] = None
    topics_before: List[Topic] = Field(default_factory=list)
    created_at: str = Field(default_factory=now_iso)


class StoryStatus(str, Enum):
    GENERATING = "generating"
    AWAITING_BLUEPRINT = "awaiting_blueprint"   # 蓝图已生成，等待确认 / 修改
    AWAITING_CHOICE = "awaiting_choice"         # 章节已生成，等待选择下一章方向
    FAILED = "failed"


class Job(BaseModel):
    kind: str = ""                  # blueprint / chapter / regenerate
    message: str = ""
    progress: int = 0
    started_at: str = ""
    params: dict = Field(default_factory=dict)


class StorySession(BaseModel):
    id: str = Field(default_factory=lambda: short_id("story"))
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    seed: str = ""
    source_name: str = ""
    source_digest: str = ""
    style_id: str = "realistic"
    style_notes: str = ""
    status: StoryStatus = StoryStatus.GENERATING
    error: Optional[str] = None
    job: Optional[Job] = None
    blueprint: Optional[Blueprint] = None
    blueprint_notes: List[str] = Field(default_factory=list)
    world: Optional[WorldState] = None
    chapters: List[Chapter] = Field(default_factory=list)
    topics: List[Topic] = Field(default_factory=list)

    def public_dict(self) -> dict:
        """接口返回用：去掉体积大的快照。"""
        data = self.model_dump(mode="json", exclude={"chapters": {"__all__": {"world_before", "topics_before"}}})
        if data.get("world"):
            data["world"]["timeline_count"] = len(data["world"].get("timeline") or [])
            data["world"].pop("timeline", None)
        return data

    def list_item(self) -> dict:
        return {
            "id": self.id,
            "title": (self.blueprint.title if self.blueprint else "") or "生成中…",
            "premise": self.blueprint.premise if self.blueprint else self.seed[:80],
            "status": self.status.value,
            "style_id": self.style_id,
            "chapter_count": len(self.chapters),
            "updated_at": self.updated_at,
        }
