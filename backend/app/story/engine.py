"""
故事引擎：先让世界运行，再把发生的事写出来。

每章流程：
  导演安排场景 → 角色在各自信息边界内轮流行动 → 设定一致性审校
  → 叙述者依据事件日志 + 上一章结尾写正文 → 去 AI 腔润色
  → 把状态变化写回 WorldState → 依据新状态生成下一章选项
"""

from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Tuple

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from . import prompts as P
from .memory import (
    character_card,
    format_event,
    knowledge_text,
    relationships_text,
    relevant_events,
    score,
    world_overview,
)
from .styles import BASE_RULES, get_style
from .models import (
    Blueprint,
    Chapter,
    Character,
    Event,
    Fact,
    ScenePlan,
    StorySession,
    Topic,
    WorldState,
    short_id,
)

logger = get_logger("story.engine")

Progress = Callable[[str, int], None]


def _msgs(system: str, user: str) -> List[Dict[str, str]]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _as_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [x.strip() for x in value.replace("、", ",").split(",") if x.strip()]
    return []


def _as_dicts(value) -> List[dict]:
    return [x for x in (value or []) if isinstance(x, dict)]


def opening_topic(bp: Blueprint) -> Topic:
    return Topic(
        title="开场",
        summary=bp.opening_situation or bp.premise,
        focus_characters=[bp.protagonist] if bp.protagonist else [],
    )


def add_character(world: WorldState, raw: dict, introduced_in: int = 0) -> Optional[Character]:
    """把一个人物加入世界：秘密记为只有本人知道的事实，可附带他对已有人物的看法。
    名字为空或与已有人物重名时返回 None。"""
    name = str(raw.get("name") or "").strip()
    if not name or world.char(name):
        return None
    c = Character(
        id=short_id("c"),
        name=name,
        aliases=[str(a) for a in _as_list(raw.get("aliases"))],
        role=str(raw.get("role") or ""),
        description=str(raw.get("description") or ""),
        personality=str(raw.get("personality") or ""),
        voice=str(raw.get("voice") or ""),
        goal=str(raw.get("goal") or ""),
        location=str(raw.get("location") or ""),
        introduced_in=introduced_in,
    )
    world.characters.append(c)
    secret = str(raw.get("secret") or "").strip()
    if secret:
        world.facts.append(
            Fact(id=short_id("f"), content=f"{c.name}：{secret}", known_by=[c.id], chapter_no=introduced_in)
        )
    for rel in _as_dicts(raw.get("relationships")):
        other = world.char(str(rel.get("to") or ""))
        if other and other.id != c.id and rel.get("description"):
            c.relationships[other.id] = str(rel["description"])
    return c


class StoryEngine:
    def __init__(self, progress: Optional[Progress] = None, style_id: str = "", style_notes: str = ""):
        self.llm = LLMClient()
        self.writer = LLMClient(Config.LLM_WRITER_MODEL_NAME) if Config.LLM_WRITER_MODEL_NAME else self.llm
        self.progress: Progress = progress or (lambda msg, pct: None)
        self.style = get_style(style_id)
        self.style_notes = (style_notes or "").strip()

    def _style(self, part: str) -> str:
        """取当前风格在某个环节的指导语，并附上用户的自定义补充。"""
        return P.style_block(self.style.name, getattr(self.style, part), self.style_notes)

    # ------------------------------------------------------------------ 素材
    def digest_source(self, text: str) -> str:
        """长素材分段整理再合并，避免直接截断丢信息。"""
        text = (text or "").strip()
        if len(text) <= Config.SOURCE_DIRECT_LIMIT:
            return text
        size = max(Config.SOURCE_CHUNK_SIZE, math.ceil(len(text) / Config.SOURCE_MAX_CHUNKS))
        chunks = [text[i : i + size] for i in range(0, len(text), size)]
        notes = []
        for i, chunk in enumerate(chunks, 1):
            self.progress(f"整理素材 {i}/{len(chunks)}", 5 + int(45 * i / len(chunks)))
            notes.append(
                self.llm.chat(
                    _msgs(P.DIGEST_CHUNK_SYSTEM, P.DIGEST_CHUNK_USER.format(index=i, total=len(chunks), text=chunk)),
                    temperature=0.2,
                    max_tokens=3000,
                )
            )
        self.progress("合并素材笔记", 55)
        while len(notes) > 1 and sum(len(n) for n in notes) > 12000:
            groups = [notes[i : i + 6] for i in range(0, len(notes), 6)]
            notes = [self._merge_notes(g, 2500) for g in groups]
        return self._merge_notes(notes, 4000) if len(notes) > 1 else notes[0]

    def _merge_notes(self, notes: List[str], limit: int) -> str:
        joined = "\n\n".join(f"【片段 {i + 1}】\n{n}" for i, n in enumerate(notes))
        return self.llm.chat(
            _msgs(P.DIGEST_MERGE_SYSTEM, P.DIGEST_MERGE_USER.format(limit=limit, notes=joined)),
            temperature=0.2,
            max_tokens=6000,
        )

    # ------------------------------------------------------------------ 蓝图
    def build_blueprint(self, session: StorySession, instruction: str = "") -> Blueprint:
        previous = ""
        if session.blueprint:
            previous = "已有蓝图（请在此基础上按修改意见调整，没提到的部分尽量保持）：\n" + session.blueprint.model_dump_json()
        if session.blueprint_notes:
            previous += "\n历次修改意见：" + "；".join(session.blueprint_notes)
        messages = _msgs(
            P.BLUEPRINT_SYSTEM.format(style=self._style("blueprint")),
            P.BLUEPRINT_USER.format(
                seed=session.seed or "（未提供，依据素材）",
                digest=session.source_digest or "（无）",
                previous=previous,
                instruction=f"本次修改意见：{instruction}" if instruction else "",
            ),
        )
        data: dict = {}
        for attempt in range(2):
            try:
                data = self.llm.chat_json(messages, temperature=0.7, max_tokens=12000)
            except ValueError as exc:  # JSON 无法解析
                logger.warning("蓝图 JSON 解析失败（第 %d 次）: %s", attempt + 1, exc)
                data = {}
            if any(isinstance(c, dict) and c.get("name") for c in data.get("characters") or []):
                break
            logger.warning("蓝图里没有人物（第 %d 次），重新生成", attempt + 1)
        bp = Blueprint(
            title=str(data.get("title") or "未命名故事"),
            premise=str(data.get("premise") or session.seed[:100]),
            genre=str(data.get("genre") or ""),
            style=str(data.get("style") or ""),
            setting=str(data.get("setting") or ""),
            core_conflict=str(data.get("core_conflict") or ""),
            ending_direction=str(data.get("ending_direction") or ""),
            opening_situation=str(data.get("opening_situation") or ""),
            protagonist=str(data.get("protagonist") or ""),
            summary=str(data.get("summary") or ""),
            selling_points=[str(x) for x in _as_list(data.get("selling_points"))],
            reader_promises=[str(x) for x in _as_list(data.get("reader_promises"))],
            characters=[c for c in _as_dicts(data.get("characters")) if c.get("name")],
            relationships=_as_dicts(data.get("relationships")),
            locations=[str(x) for x in _as_list(data.get("locations"))],
            rules=[str(x) for x in _as_list(data.get("rules"))],
            opening_facts=_as_dicts(data.get("opening_facts")),
        )
        if not bp.characters:
            raise ValueError("蓝图中没有人物，请重新生成")
        if not bp.protagonist:
            bp.protagonist = bp.characters[0]["name"]
        return bp

    @staticmethod
    def init_world(bp: Blueprint) -> WorldState:
        world = WorldState(
            time_label="故事开始",
            setting=bp.setting,
            rules=list(bp.rules),
            locations=list(bp.locations),
        )
        for raw in bp.characters:
            add_character(world, raw)
        for rel in bp.relationships:
            a, b = world.char(str(rel.get("from") or "")), world.char(str(rel.get("to") or ""))
            if a and b and a.id != b.id:
                a.relationships[b.id] = str(rel.get("description") or "")
        for f in bp.opening_facts:
            content = str(f.get("content") or "").strip()
            if not content:
                continue
            known = _as_list(f.get("known_by"))
            public = bool(f.get("public")) or any(str(k) in ("all", "所有人", "众所周知") for k in known)
            world.facts.append(Fact(id=short_id("f"), content=content, known_by=world.resolve_ids(known), public=public))
        return world

    # ------------------------------------------------------------------ 章节
    def generate_chapter(
        self,
        bp: Blueprint,
        base_world: WorldState,
        prev_chapters: List[Chapter],
        topic: Topic,
        base_topics: List[Topic],
    ) -> Tuple[Chapter, WorldState, List[Topic]]:
        """在 base_world 的副本上推演一章；全部成功后才由调用方提交。"""
        world = base_world.model_copy(deep=True)
        no = len(prev_chapters) + 1
        chapter = Chapter(
            no=no,
            topic=topic,
            world_before=base_world.model_copy(deep=True),
            topics_before=[t.model_copy() for t in base_topics],
            style_id=self.style.id,
            pacing=self.style.pacing_task(no),
        )

        self.progress(f"导演安排场景（{self.style.name}）", 5)
        self._direct(bp, world, prev_chapters, topic, chapter)

        events: List[Event] = []
        for idx, scene in enumerate(chapter.scenes, 1):
            base = 10 + int(50 * (idx - 1) / len(chapter.scenes))
            self.progress(f"场景 {idx}/{len(chapter.scenes)}：{scene.location} — 角色行动中", base)
            events.extend(self._run_scene(world, chapter, idx, scene, events))
        if not events:
            raise RuntimeError("本章没有产生任何事件，请重试")

        self.progress("设定一致性审校", 62)
        events = self._check_consistency(world, chapter, events)
        chapter.events = events

        self.progress("根据事件写正文", 70)
        prev_tail = prev_chapters[-1].content[-Config.PREV_TAIL_CHARS :] if prev_chapters else ""
        chapter.draft = self._narrate(bp, world, chapter, prev_tail)

        self.progress("润色：去除 AI 腔", 82)
        chapter.content = self._revise(chapter.draft)

        self.progress("更新世界状态", 90)
        self._update_state(world, chapter)

        self.progress("生成下一章方向", 96)
        topics = self._topics(bp, world, chapter)
        return chapter, world, topics

    # -------- 导演
    def _direct(self, bp: Blueprint, world: WorldState, prev: List[Chapter], topic: Topic, chapter: Chapter) -> None:
        focus = world.resolve_ids(topic.focus_characters)
        recent = "\n".join(f"第{c.no}章 {c.title}：{c.summary}" for c in prev[-5:]) or "（这是第一章）"
        if not prev:
            recent += f"\n开场情境：{bp.opening_situation}"
        topic_text = f"{topic.title}：{topic.summary}" + (
            f"（重点人物：{'、'.join(topic.focus_characters)}）" if topic.focus_characters else ""
        )
        data = self.llm.chat_json(
            _msgs(
                P.DIRECTOR_SYSTEM.format(style=self._style("director"), max_new=Config.MAX_NEW_CHARACTERS),
                P.DIRECTOR_USER.format(
                    title=bp.title,
                    setting=bp.setting,
                    core_conflict=bp.core_conflict,
                    selling_points="；".join(bp.selling_points) or "（无）",
                    reader_promises="；".join(bp.reader_promises) or "（无）",
                    ending_direction=bp.ending_direction,
                    pacing=f"本章节奏任务：{chapter.pacing}\n" if chapter.pacing else "",
                    overview=world_overview(world, query=topic_text, focus=focus),
                    recent=recent,
                    chapter_no=chapter.no,
                    topic=topic_text,
                    max_scenes=Config.MAX_SCENES,
                    max_chars=Config.SCENE_MAX_CHARACTERS,
                ),
            ),
            temperature=0.6,
            max_tokens=4000,
        )
        chapter.title = str(data.get("chapter_title") or f"第{chapter.no}章")
        chapter.time_label = str(data.get("time_label") or world.time_label)
        world.time_label = chapter.time_label

        # 先登记新人物，场景里才能引用到他们
        for raw in _as_dicts(data.get("new_characters"))[: Config.MAX_NEW_CHARACTERS]:
            c = add_character(world, raw, introduced_in=chapter.no)
            if c:
                chapter.introduced.append(c.id)

        active = [c for c in world.characters if c.active]
        if not active:
            raise RuntimeError("世界里已经没有可以行动的人物了")
        pov = next(
            (c for c in (world.char(str(data.get("pov") or "")), world.char(bp.protagonist)) if c and c.active),
            active[0],
        )
        chapter.pov = pov.id

        for raw in _as_dicts(data.get("scenes"))[: Config.MAX_SCENES]:
            present = [cid for cid in world.resolve_ids(_as_list(raw.get("present"))) if world.char(cid).active]
            present = present[: Config.SCENE_MAX_CHARACTERS]
            if not present:
                continue
            chapter.scenes.append(
                ScenePlan(
                    location=str(raw.get("location") or ""),
                    present=present,
                    situation=str(raw.get("situation") or ""),
                    world_event=str(raw.get("world_event") or ""),
                )
            )
        if not chapter.scenes:
            others = [c.id for c in active if c.id != pov.id][:1]
            chapter.scenes.append(
                ScenePlan(location=pov.location, present=[pov.id, *others], situation=topic.summary)
            )

        # 登记了却没被安排进任何场景的新人物撤掉，避免世界里堆积用不上的人
        used = {cid for s in chapter.scenes for cid in s.present} | {chapter.pov}
        unused = [cid for cid in chapter.introduced if cid not in used]
        if unused:
            world.characters = [c for c in world.characters if c.id not in unused]
            world.facts = [f for f in world.facts if not (set(f.known_by) and set(f.known_by) <= set(unused))]
            chapter.introduced = [cid for cid in chapter.introduced if cid not in unused]

    # -------- 角色行动
    def _run_scene(
        self, world: WorldState, chapter: Chapter, scene_no: int, scene: ScenePlan, earlier: List[Event]
    ) -> List[Event]:
        present = list(scene.present)
        for cid in present:
            world.char(cid).location = scene.location
        if chapter.pov in present:  # 视角人物先行动
            present.remove(chapter.pov)
            present.insert(0, chapter.pov)

        scene_events: List[Event] = []
        counter = [0]

        def add(actor: str, kind: str, content: str) -> None:
            counter[0] += 1
            scene_events.append(
                Event(
                    id=f"c{chapter.no}s{scene_no}e{counter[0]}",
                    chapter_no=chapter.no,
                    scene_no=scene_no,
                    location=scene.location,
                    actor=actor,
                    kind=kind,
                    content=content,
                    witnesses=list(present),
                )
            )

        rounds = max(1, Config.SCENE_ROUNDS)
        event_round = 1 if rounds > 1 else 0
        event_fired = not scene.world_event
        for r in range(rounds):
            if not event_fired and r >= event_round:
                add("world", "world", scene.world_event)
                event_fired = True
            acted = False
            for cid in list(present):
                decision = self._act(world, chapter, scene, cid, present, earlier + scene_events)
                kind = str(decision.get("kind") or "pass").lower()
                content = str(decision.get("content") or "").strip()
                char = world.char(cid)
                if decision.get("mood"):
                    char.mood = str(decision["mood"])
                if kind == "leave":
                    add(cid, "action", content or f"{char.name}离开了。")
                    present.remove(cid)
                    acted = True
                elif kind in ("speech", "action") and content:
                    add(cid, kind, content)
                    acted = True
            if not present:
                break
            if not acted:
                # 都没动静：如果还有没触发的外部事件，就让它提前发生，给角色一个反应的理由
                if not event_fired:
                    add("world", "world", scene.world_event)
                    event_fired = True
                    continue
                break
        return scene_events

    def _act(
        self, world: WorldState, chapter: Chapter, scene: ScenePlan, cid: str, present: List[str], so_far: List[Event]
    ) -> dict:
        me = world.char(cid)
        seen = [e for e in so_far if cid in e.witnesses or e.actor == cid][-20:]
        scene_log = "\n".join(
            ("你" if e.actor == cid else world.char_name(e.actor))
            + ("说：“" + e.content + "”" if e.kind == "speech" else "：" + e.content)
            if e.kind != "world"
            else f"（{e.content}）"
            for e in seen
        ) or "（场景刚开始）"

        query = f"{scene.situation} {scene.location} " + " ".join(world.char_name(p) for p in present)
        memories = relevant_events(world, query, involving=present, visible_to=cid, limit=6)
        recent_own = world.events_witnessed_by(cid)[-6:]
        merged = {e.id: e for e in [*memories, *recent_own]}
        mem_text = "\n".join(format_event(world, e) for e in sorted(merged.values(), key=lambda e: (e.chapter_no, e.scene_no))) or "（无）"

        others = [world.char(p) for p in present if p != cid]
        present_text = "；".join(f"{o.name}（{o.description}）" for o in others) or "只有你自己"

        try:
            return self.llm.chat_json(
                _msgs(
                    P.CHARACTER_SYSTEM.format(name=me.name, style=self.style.character),
                    P.CHARACTER_USER.format(
                        card=character_card(world, me),
                        relationships=relationships_text(world, me),
                        knowledge=knowledge_text(world, cid),
                        memories=mem_text,
                        time_label=world.time_label,
                        location=scene.location,
                        present=present_text,
                        situation=scene.situation,
                        scene_log=scene_log,
                    ),
                ),
                temperature=0.85,
                max_tokens=2000,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("角色 %s 行动失败，本轮跳过: %s", me.name, exc)
            return {"kind": "pass"}

    # -------- 一致性审校
    def _check_consistency(self, world: WorldState, chapter: Chapter, events: List[Event]) -> List[Event]:
        involved = list(dict.fromkeys(cid for e in events for cid in [e.actor, *e.witnesses] if cid != "world"))
        knowledge = "\n".join(f"【{world.char_name(cid)}】\n{knowledge_text(world, cid)}" for cid in involved)
        log = "\n".join(f"{e.id} | {world.char_name(e.actor)} | {e.kind} | {e.content}" for e in events)
        history = relevant_events(world, " ".join(e.content for e in events)[:600], involving=involved, limit=10)
        try:
            data = self.llm.chat_json(
                _msgs(
                    P.CONSISTENCY_SYSTEM,
                    P.CONSISTENCY_USER.format(
                        rules="\n".join(f"- {r}" for r in world.rules) or "（无特别规则，遵循现实逻辑）",
                        knowledge=knowledge,
                        history="\n".join(format_event(world, e) for e in history) or "（无）",
                        log=log,
                    ),
                ),
                temperature=0.1,
                max_tokens=4000,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("一致性审校失败，跳过: %s", exc)
            return events

        by_id = {e.id: e for e in events}
        dropped = set()
        for issue in _as_dicts(data.get("issues")):
            ev = by_id.get(str(issue.get("event_id") or ""))
            if not ev:
                continue
            fix = str(issue.get("fix") or "").strip()
            chapter.consistency_notes.append(
                f"{ev.id}（{world.char_name(ev.actor)}）：{issue.get('problem', '')} → {'改为：' + fix if fix else '删除'}"
            )
            if fix:
                ev.content = fix
            else:
                dropped.add(ev.id)
        return [e for e in events if e.id not in dropped]

    # -------- 写作
    def _narrate(self, bp: Blueprint, world: WorldState, chapter: Chapter, prev_tail: str) -> str:
        lines = []
        for idx, scene in enumerate(chapter.scenes, 1):
            evs = [e for e in chapter.events if e.scene_no == idx]
            if not evs:
                continue
            lines.append(f"—— 场景{idx}：{scene.location}。{scene.situation}")
            for e in evs:
                if e.kind == "speech":
                    lines.append(f"{world.char_name(e.actor)}说：“{e.content}”")
                elif e.kind == "world":
                    lines.append(f"（{e.content}）")
                else:
                    lines.append(f"{world.char_name(e.actor)}：{e.content}")
        involved = list(dict.fromkeys(e.actor for e in chapter.events if e.actor != "world"))
        cards = "\n".join(character_card(world, world.char(cid), private=False) + f"  说话方式：{world.char(cid).voice}" for cid in involved)
        return self.writer.chat(
            _msgs(
                P.NARRATOR_SYSTEM.format(style=self._style("narrator"), base_rules=BASE_RULES),
                P.NARRATOR_USER.format(
                    title=bp.title,
                    style=bp.style or "第三人称",
                    pov=world.char_name(chapter.pov),
                    chapter_no=chapter.no,
                    chapter_title=chapter.title,
                    time_label=chapter.time_label,
                    pacing=f"本章节奏任务：{chapter.pacing}\n" if chapter.pacing else "",
                    cards=cards,
                    prev_tail=prev_tail or f"（这是第一章。开场情境：{bp.opening_situation}）",
                    log="\n".join(lines),
                    min_len=self.style.length[0],
                    max_len=self.style.length[1],
                    ending=self.style.ending,
                ),
            ),
            temperature=self.style.narrator_temperature,
            max_tokens=12000,
        )

    def _revise(self, draft: str) -> str:
        try:
            revised = self.writer.chat(
                _msgs(
                    P.REVISE_SYSTEM.format(style=self._style("narrator"), base_rules=BASE_RULES),
                    P.REVISE_USER.format(revise=self.style.revise, ending=self.style.ending, text=draft),
                ),
                temperature=0.4,
                max_tokens=12000,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("润色失败，使用初稿: %s", exc)
            return draft
        # 防止被截断或被改成摘要
        return revised if len(revised) >= len(draft) * 0.6 else draft

    # -------- 状态回写
    def _update_state(self, world: WorldState, chapter: Chapter) -> None:
        log = "\n".join(format_event(world, e) for e in chapter.events)
        data = self.llm.chat_json(
            _msgs(P.STATE_SYSTEM, P.STATE_USER.format(overview=world_overview(world), log=log)),
            temperature=0.2,
            max_tokens=6000,
        )
        chapter.summary = str(data.get("summary") or "")
        if data.get("time_label"):
            world.time_label = str(data["time_label"])

        for raw in _as_dicts(data.get("characters")):
            c = world.char(str(raw.get("name") or ""))
            if not c:
                continue
            for field in ("location", "mood", "goal", "status"):
                val = str(raw.get(field) or "").strip()
                if val:
                    setattr(c, field, val)
            if raw.get("active") is False:
                c.active = False

        for raw in _as_dicts(data.get("new_facts")):
            content = str(raw.get("content") or "").strip()
            if content:
                world.facts.append(
                    Fact(
                        id=short_id("f"),
                        content=content,
                        known_by=world.resolve_ids(_as_list(raw.get("known_by"))),
                        public=bool(raw.get("public")),
                        chapter_no=chapter.no,
                    )
                )

        for raw in _as_dicts(data.get("learned")):
            text = str(raw.get("fact") or "")
            best = max(world.facts, key=lambda f: score(text, f.content), default=None)
            if best and score(text, best.content) > 0.3:
                for cid in world.resolve_ids(_as_list(raw.get("learned_by"))):
                    if cid not in best.known_by:
                        best.known_by.append(cid)

        for raw in _as_dicts(data.get("relationships")):
            a, b = world.char(str(raw.get("from") or "")), world.char(str(raw.get("to") or ""))
            if a and b and a.id != b.id and raw.get("description"):
                a.relationships[b.id] = str(raw["description"])

        for done in _as_list(data.get("resolved_threads")):
            world.open_threads = [t for t in world.open_threads if t != done and score(str(done), t) < 0.5]
        for new in _as_list(data.get("new_threads")):
            if new not in world.open_threads:
                world.open_threads.append(str(new))
        world.open_threads = world.open_threads[-12:]
        world.timeline.extend(chapter.events)

    # -------- 下一章方向
    def _topics(self, bp: Blueprint, world: WorldState, chapter: Chapter) -> List[Topic]:
        try:
            data = self.llm.chat_json(
                _msgs(
                    P.TOPICS_SYSTEM.format(style=self._style("topics")),
                    P.TOPICS_USER.format(
                        overview=world_overview(world),
                        summary=chapter.summary,
                        reader_promises="；".join(bp.reader_promises) or "（无）",
                        ending_direction=bp.ending_direction,
                    ),
                ),
                temperature=0.8,
                max_tokens=3000,
            )
            raw_topics = _as_dicts(data.get("topics"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("生成方向失败: %s", exc)
            raw_topics = []
        topics = [
            Topic(
                title=str(t.get("title")),
                summary=str(t.get("summary") or ""),
                focus_characters=[str(x) for x in _as_list(t.get("focus_characters"))],
            )
            for t in raw_topics
            if t.get("title")
        ][:3]
        for thread in world.open_threads[::-1]:
            if len(topics) >= 3:
                break
            topics.append(Topic(title=thread[:30], summary=thread))
        return topics

