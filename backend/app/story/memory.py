"""
从 WorldState 中检索上下文。

不依赖外部图数据库：按实体（角色）、关系、角色可见范围直接查询，
再用中文字符二元组重叠给历史事件打分，挑出与当前情境相关的旧事件。
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Set

from .models import Character, Event, WorldState

_PUNCT = re.compile(r"[\s，。！？、；：“”‘’（）《》【】,.!?;:\"'()\[\]<>…—\-]+")


def _bigrams(text: str) -> Set[str]:
    text = _PUNCT.sub("", text or "")
    if len(text) < 2:
        return {text} if text else set()
    return {text[i : i + 2] for i in range(len(text) - 1)}


def score(query: str, text: str) -> float:
    q, t = _bigrams(query), _bigrams(text)
    if not q or not t:
        return 0.0
    return len(q & t) / (len(q) ** 0.5 * len(t) ** 0.5)


def format_event(world: WorldState, e: Event) -> str:
    who = world.char_name(e.actor)
    if e.kind == "speech":
        return f"[第{e.chapter_no}章·{e.location}] {who}说：“{e.content}”"
    if e.kind == "world":
        return f"[第{e.chapter_no}章·{e.location}] {e.content}"
    return f"[第{e.chapter_no}章·{e.location}] {who}：{e.content}"


def relevant_events(
    world: WorldState,
    query: str,
    involving: Iterable[str] = (),
    visible_to: Optional[str] = None,
    exclude_chapter: Optional[int] = None,
    limit: int = 8,
) -> List[Event]:
    involving = set(involving)
    pool = world.events_witnessed_by(visible_to) if visible_to else world.timeline
    scored = []
    for e in pool:
        if exclude_chapter is not None and e.chapter_no == exclude_chapter:
            continue
        s = score(query, e.content)
        if involving and (e.actor in involving or involving & set(e.witnesses)):
            s += 0.15
        if s > 0.05:
            scored.append((s, e))
    scored.sort(key=lambda x: x[0], reverse=True)
    picked = [e for _, e in scored[:limit]]
    picked.sort(key=lambda e: (e.chapter_no, e.scene_no))
    return picked


def character_card(world: WorldState, c: Character, private: bool = True) -> str:
    lines = [f"{c.name}（{c.role}）：{c.description}"]
    if private:
        if c.personality:
            lines.append(f"  性格：{c.personality}")
        if c.voice:
            lines.append(f"  说话方式：{c.voice}")
        if c.goal:
            lines.append(f"  当前目标：{c.goal}")
    state = "，".join(x for x in [c.location and f"在{c.location}", c.mood and f"情绪{c.mood}", c.status] if x)
    if state:
        lines.append(f"  当前状态：{state}")
    if not c.active:
        lines.append("  （已离场 / 无法行动）")
    return "\n".join(lines)


def relationships_text(world: WorldState, c: Character) -> str:
    rows = [f"- 对{world.char_name(oid)}：{desc}" for oid, desc in c.relationships.items() if desc]
    return "\n".join(rows) or "（无特别关系）"


def knowledge_text(world: WorldState, cid: str) -> str:
    facts = world.facts_known_by(cid)
    return "\n".join(f"- {f.content}" for f in facts) or "（无）"


def world_overview(world: WorldState, query: str = "", focus: Iterable[str] = ()) -> str:
    """导演 / 状态更新使用的全知视角摘要。"""
    focus = list(focus)
    parts = [f"当前时间：{world.time_label or '未指定'}"]
    if world.rules:
        parts.append("世界规则：\n" + "\n".join(f"- {r}" for r in world.rules))
    active = [c for c in world.characters if c.active]
    gone = [c for c in world.characters if not c.active]
    parts.append("角色：\n" + "\n".join(character_card(world, c) for c in active))
    if gone:
        # 已离场的人物只留一行，避免越写越长
        parts.append("已离场（不能再出场）：" + "；".join(f"{c.name}（{c.status or c.role}）" for c in gone[-30:]))
    active_ids = {c.id for c in active}
    rel_rows = []
    for c in active:
        for oid, desc in c.relationships.items():
            if desc and oid in active_ids:
                rel_rows.append(f"- {c.name} → {world.char_name(oid)}：{desc}")
    if rel_rows:
        parts.append("关系：\n" + "\n".join(rel_rows[:40]))
    if world.facts:
        fact_rows = []
        for f in world.facts[-60:]:
            who = "众所周知" if f.public else "、".join(world.char_name(x) for x in f.known_by) or "无人知晓"
            fact_rows.append(f"- {f.content}（知情者：{who}）")
        parts.append("事实与秘密：\n" + "\n".join(fact_rows))
    if world.open_threads:
        parts.append("未解决的线索：\n" + "\n".join(f"- {t}" for t in world.open_threads))
    if query:
        evs = relevant_events(world, query, involving=focus, limit=10)
        if evs:
            parts.append("相关的过往事件：\n" + "\n".join(format_event(world, e) for e in evs))
    return "\n\n".join(parts)
