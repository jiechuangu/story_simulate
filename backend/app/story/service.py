"""
故事会话的业务操作与后台任务。

所有耗时操作都走 start_job：状态（进度、消息、参数）持久化在会话里，
失败后可以用相同参数重试；后端重启后由 store.recover_interrupted 标记为失败。
"""

from __future__ import annotations

import os
import threading
from typing import Optional

from ..config import Config
from ..utils.logger import get_logger
from . import store
from .engine import StoryEngine, opening_topic
from .styles import DEFAULT_STYLE, STYLES
from .models import Job, StorySession, StoryStatus, Topic, now_iso

logger = get_logger("story.service")


class Busy(Exception):
    pass


def _source_path(story_id: str) -> str:
    return os.path.join(Config.STORIES_DIR, story_id, "source.txt")


def create_session(
    seed: str, source_text: str = "", source_name: str = "", style_id: str = "", style_notes: str = ""
) -> StorySession:
    session = StorySession(
        seed=seed.strip(),
        source_name=source_name,
        status=StoryStatus.AWAITING_BLUEPRINT,
        style_id=_check_style(style_id),
        style_notes=(style_notes or "").strip(),
    )
    store.save(session)
    if source_text.strip():
        with open(_source_path(session.id), "w", encoding="utf-8") as f:
            f.write(source_text)
    start_job(session.id, "blueprint", {})
    return session


def start_job(story_id: str, kind: str, params: dict) -> StorySession:
    with store.story_lock(story_id):
        session = store.load(story_id)
        if not session:
            raise KeyError(story_id)
        if session.status == StoryStatus.GENERATING:
            raise Busy("故事正在生成中，请稍候")
        session.status = StoryStatus.GENERATING
        session.error = None
        session.job = Job(kind=kind, message="准备中", progress=0, started_at=now_iso(), params=params)
        store.save(session)
    threading.Thread(target=_run_job, args=(story_id, kind, params), daemon=True).start()
    return session


def retry(story_id: str) -> StorySession:
    session = store.load(story_id)
    if not session:
        raise KeyError(story_id)
    if session.status != StoryStatus.FAILED or not session.job:
        raise ValueError("当前没有可重试的任务")
    return start_job(story_id, session.job.kind, session.job.params)


def _run_job(story_id: str, kind: str, params: dict) -> None:
    session = store.load(story_id)

    def progress(message: str, pct: int) -> None:
        session.job.message = message
        session.job.progress = pct
        store.save(session)

    try:
        engine = StoryEngine(progress, style_id=session.style_id, style_notes=session.style_notes)
        if kind == "blueprint":
            _job_blueprint(engine, session, params.get("instruction", ""))
        elif kind in ("first_chapter", "choose", "regenerate"):
            _job_chapter(engine, session, kind, params)
        else:
            raise ValueError(f"未知任务类型: {kind}")
        session.job.progress = 100
        session.job.message = "完成"
    except Exception as exc:  # noqa: BLE001
        logger.exception("任务 %s 失败（%s）", kind, story_id)
        session.status = StoryStatus.FAILED
        session.error = str(exc)
    store.save(session)


def _job_blueprint(engine: StoryEngine, session: StorySession, instruction: str) -> None:
    src = _source_path(session.id)
    if os.path.exists(src) and not session.source_digest:
        with open(src, "r", encoding="utf-8") as f:
            session.source_digest = engine.digest_source(f.read())
        store.save(session)
    engine.progress("生成故事蓝图", 70)
    session.blueprint = engine.build_blueprint(session, instruction)
    if instruction:
        session.blueprint_notes.append(instruction)
    session.status = StoryStatus.AWAITING_BLUEPRINT


def _job_chapter(engine: StoryEngine, session: StorySession, kind: str, params: dict) -> None:
    bp = session.blueprint
    if not bp:
        raise ValueError("还没有蓝图")

    if kind == "first_chapter":
        base_world = engine.init_world(bp)
        prev, base_topics, topic = [], [], opening_topic(bp)
    elif kind == "choose":
        base_world, prev, base_topics = session.world, list(session.chapters), list(session.topics)
        topic = Topic.model_validate(params["topic"])
    else:  # regenerate：回到最后一章之前的状态，用同一方向重写
        last = session.chapters[-1]
        base_world, prev, base_topics = last.world_before, list(session.chapters[:-1]), list(last.topics_before)
        topic = last.topic or opening_topic(bp)

    chapter, world, topics = engine.generate_chapter(bp, base_world, prev, topic, base_topics)
    # 全部成功后一次性提交
    session.chapters = prev + [chapter]
    session.world = world
    session.topics = topics
    session.status = StoryStatus.AWAITING_CHOICE


# ---------------------------------------------------------------- 同步操作

def choose(story_id: str, topic_id: Optional[str], custom: str = "") -> StorySession:
    session = store.load(story_id)
    if not session:
        raise KeyError(story_id)
    if session.status == StoryStatus.GENERATING:
        raise Busy("故事正在生成中，请稍候")
    if not session.world:
        raise ValueError("请先确认蓝图")
    if custom.strip():
        topic = Topic(title=custom.strip()[:40], summary=custom.strip(), custom=True)
    else:
        topic = next((t for t in session.topics if t.id == topic_id), None)
        if not topic:
            raise ValueError("所选方向不存在")
    return start_job(story_id, "choose", {"topic": topic.model_dump(mode="json")})


def _check_style(style_id: str) -> str:
    style_id = style_id or DEFAULT_STYLE
    if style_id not in STYLES:
        raise ValueError(f"未知的风格: {style_id}")
    return style_id


def set_style(story_id: str, style_id: str, style_notes: str) -> StorySession:
    """切换风格：对之后生成的内容（蓝图重生成、下一章、重写本章）生效，已写好的章节不变。"""
    with store.story_lock(story_id):
        session = store.load(story_id)
        if not session:
            raise KeyError(story_id)
        if session.status == StoryStatus.GENERATING:
            raise Busy("故事正在生成中，请稍候")
        session.style_id = _check_style(style_id)
        session.style_notes = (style_notes or "").strip()
        store.save(session)
        return session


def rewind(story_id: str, keep_chapters: int) -> StorySession:
    """回退到第 keep_chapters 章结束时的状态（之后的章节删除，恢复当时的方向选项）。"""
    with store.story_lock(story_id):
        session = store.load(story_id)
        if not session:
            raise KeyError(story_id)
        if session.status == StoryStatus.GENERATING:
            raise Busy("故事正在生成中，请稍候")
        if keep_chapters < 1 or keep_chapters >= len(session.chapters):
            raise ValueError("无效的章节号")
        nxt = session.chapters[keep_chapters]
        session.world = nxt.world_before
        session.topics = nxt.topics_before
        session.chapters = session.chapters[:keep_chapters]
        session.status = StoryStatus.AWAITING_CHOICE
        session.error = None
        session.job = None
        store.save(session)
        return session
