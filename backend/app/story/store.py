"""
故事会话持久化：uploads/stories/<id>/session.json（原子写入），并导出章节 markdown。
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from typing import Dict, List, Optional

from ..config import Config
from ..utils.logger import get_logger
from .models import StorySession, StoryStatus, now_iso

logger = get_logger("story.store")

_locks: Dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


def story_lock(story_id: str) -> threading.RLock:
    with _locks_guard:
        if story_id not in _locks:
            _locks[story_id] = threading.RLock()
        return _locks[story_id]


def _dir(story_id: str) -> str:
    if not story_id or any(c in story_id for c in "/\\.") :
        raise ValueError("非法的 story id")
    return os.path.join(Config.STORIES_DIR, story_id)


def _atomic_write(path: str, text: str) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    # Windows 上若文件正被其他进程（杀毒、索引）短暂占用，os.replace 会失败，稍等重试
    for attempt in range(10):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.05 * (attempt + 1))


def save(session: StorySession) -> None:
    session.updated_at = now_iso()
    d = _dir(session.id)
    os.makedirs(d, exist_ok=True)
    with story_lock(session.id):
        _atomic_write(os.path.join(d, "session.json"), session.model_dump_json(indent=1))
        _atomic_write(os.path.join(d, "story.md"), render_markdown(session))


def load(story_id: str) -> Optional[StorySession]:
    try:
        path = os.path.join(_dir(story_id), "session.json")
    except ValueError:
        return None
    with story_lock(story_id):
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return StorySession.model_validate(json.load(f))


def list_all(limit: int = 50) -> List[StorySession]:
    if not os.path.isdir(Config.STORIES_DIR):
        return []
    items = []
    for name in os.listdir(Config.STORIES_DIR):
        try:
            s = load(name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("读取故事 %s 失败: %s", name, exc)
            continue
        if s:
            items.append(s)
    items.sort(key=lambda s: s.updated_at, reverse=True)
    return items[:limit]


def delete(story_id: str) -> bool:
    d = _dir(story_id)
    if not os.path.isdir(d):
        return False
    shutil.rmtree(d)
    return True


def markdown_path(story_id: str) -> str:
    return os.path.join(_dir(story_id), "story.md")


def render_markdown(session: StorySession) -> str:
    parts = []
    if session.blueprint:
        parts.append(f"# {session.blueprint.title}\n\n> {session.blueprint.premise}\n")
    for ch in session.chapters:
        parts.append(f"## 第{ch.no}章 {ch.title}\n\n{ch.content}\n")
    return "\n".join(parts)


def recover_interrupted() -> int:
    """后端重启时，把仍处于 generating 的会话标记为失败，便于用户重试。"""
    count = 0
    for s in list_all(limit=10_000):
        if s.status == StoryStatus.GENERATING:
            s.status = StoryStatus.FAILED
            s.error = "后端重启导致任务中断，可点击“重试”继续。"
            save(s)
            count += 1
    return count
