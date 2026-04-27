"""
Story MVP service.

Implements a minimal interactive fiction loop:
1. Generate a story bible from the project seed.
2. Generate one chapter at a time.
3. After each chapter, propose k next-chapter topics.
4. Wait for the user to choose a topic before continuing.
"""

import json
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from ..config import Config
from ..models.project import ProjectManager
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger

logger = get_logger("mirofish.story_mvp")


class StoryStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    WAITING_FOR_CHOICE = "waiting_for_choice"
    FAILED = "failed"


@dataclass
class TopicCandidate:
    topic_id: str
    title: str
    summary: str
    promise: str = ""
    focus_characters: List[str] = field(default_factory=list)
    tension_type: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic_id": self.topic_id,
            "title": self.title,
            "summary": self.summary,
            "promise": self.promise,
            "focus_characters": self.focus_characters,
            "tension_type": self.tension_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TopicCandidate":
        return cls(
            topic_id=data["topic_id"],
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            promise=data.get("promise", ""),
            focus_characters=data.get("focus_characters") or [],
            tension_type=data.get("tension_type", ""),
        )


@dataclass
class StoryChapter:
    chapter_no: int
    title: str
    topic_title: str
    topic_summary: str
    summary: str
    content: str
    outcome: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_no": self.chapter_no,
            "title": self.title,
            "topic_title": self.topic_title,
            "topic_summary": self.topic_summary,
            "summary": self.summary,
            "content": self.content,
            "outcome": self.outcome,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryChapter":
        return cls(
            chapter_no=data["chapter_no"],
            title=data.get("title", ""),
            topic_title=data.get("topic_title", ""),
            topic_summary=data.get("topic_summary", ""),
            summary=data.get("summary", ""),
            content=data.get("content", ""),
            outcome=data.get("outcome") or {},
            created_at=data.get("created_at", datetime.now().isoformat()),
        )


@dataclass
class StoryReport:
    report_id: str
    simulation_id: str
    project_id: str
    graph_id: Optional[str]
    simulation_requirement: str
    status: StoryStatus
    created_at: str
    updated_at: str
    title: str = ""
    premise: str = ""
    style: str = ""
    story_bible: Dict[str, Any] = field(default_factory=dict)
    chapters: List[StoryChapter] = field(default_factory=list)
    topic_candidates: List[TopicCandidate] = field(default_factory=list)
    selected_topics: List[Dict[str, Any]] = field(default_factory=list)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        chapter_blocks = [f"## Chapter {c.chapter_no}: {c.title}\n\n{c.content}" for c in self.chapters]
        markdown = ""
        if self.title:
            markdown += f"# {self.title}\n\n"
        if self.premise:
            markdown += f"> {self.premise}\n\n"
        markdown += "\n\n".join(chapter_blocks)
        return {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "project_id": self.project_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "title": self.title,
            "premise": self.premise,
            "style": self.style,
            "story_bible": self.story_bible,
            "chapters": [c.to_dict() for c in self.chapters],
            "topic_candidates": [t.to_dict() for t in self.topic_candidates],
            "selected_topics": self.selected_topics,
            "latest_chapter": self.chapters[-1].to_dict() if self.chapters else None,
            "markdown_content": markdown,
            "outline": {
                "title": self.title or "Interactive Story",
                "summary": self.premise,
                "sections": [
                    {"title": f"Chapter {chapter.chapter_no}: {chapter.title}"}
                    for chapter in self.chapters
                ],
            },
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryReport":
        status = data.get("status", StoryStatus.PENDING.value)
        return cls(
            report_id=data["report_id"],
            simulation_id=data["simulation_id"],
            project_id=data["project_id"],
            graph_id=data.get("graph_id"),
            simulation_requirement=data.get("simulation_requirement", ""),
            status=StoryStatus(status),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            title=data.get("title", ""),
            premise=data.get("premise", ""),
            style=data.get("style", ""),
            story_bible=data.get("story_bible") or {},
            chapters=[StoryChapter.from_dict(item) for item in data.get("chapters") or []],
            topic_candidates=[
                TopicCandidate.from_dict(item) for item in data.get("topic_candidates") or []
            ],
            selected_topics=data.get("selected_topics") or [],
            logs=data.get("logs") or [],
            error=data.get("error"),
        )


class StoryReportManager:
    REPORTS_DIR = os.path.join(Config.UPLOAD_FOLDER, "reports")
    _write_lock = threading.Lock()

    @classmethod
    def _ensure_reports_dir(cls) -> None:
        os.makedirs(cls.REPORTS_DIR, exist_ok=True)

    @classmethod
    def _get_report_dir(cls, report_id: str) -> str:
        return os.path.join(cls.REPORTS_DIR, report_id)

    @classmethod
    def _get_meta_path(cls, report_id: str) -> str:
        return os.path.join(cls._get_report_dir(report_id), "meta.json")

    @classmethod
    def _get_full_markdown_path(cls, report_id: str) -> str:
        return os.path.join(cls._get_report_dir(report_id), "full_report.md")

    @classmethod
    def _get_agent_log_path(cls, report_id: str) -> str:
        return os.path.join(cls._get_report_dir(report_id), "agent_log.jsonl")

    @classmethod
    def _ensure_report_dir(cls, report_id: str) -> str:
        cls._ensure_reports_dir()
        report_dir = cls._get_report_dir(report_id)
        os.makedirs(report_dir, exist_ok=True)
        return report_dir

    @classmethod
    def save_report(cls, report: StoryReport) -> None:
        report.updated_at = datetime.now().isoformat()
        cls._ensure_report_dir(report.report_id)
        with cls._write_lock:
            with open(cls._get_meta_path(report.report_id), "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
            with open(cls._get_full_markdown_path(report.report_id), "w", encoding="utf-8") as f:
                f.write(report.to_dict()["markdown_content"])

    @classmethod
    def get_report(cls, report_id: str) -> Optional[StoryReport]:
        meta_path = cls._get_meta_path(report_id)
        if not os.path.exists(meta_path):
            return None
        with open(meta_path, "r", encoding="utf-8") as f:
            return StoryReport.from_dict(json.load(f))

    @classmethod
    def get_report_by_simulation(cls, simulation_id: str) -> Optional[StoryReport]:
        cls._ensure_reports_dir()
        latest = None
        for report_id in os.listdir(cls.REPORTS_DIR):
            report = cls.get_report(report_id)
            if not report or report.simulation_id != simulation_id:
                continue
            if latest is None or report.updated_at > latest.updated_at:
                latest = report
        return latest

    @classmethod
    def list_reports(cls, simulation_id: Optional[str] = None, limit: int = 50) -> List[StoryReport]:
        cls._ensure_reports_dir()
        items: List[StoryReport] = []
        for report_id in os.listdir(cls.REPORTS_DIR):
            report = cls.get_report(report_id)
            if not report:
                continue
            if simulation_id and report.simulation_id != simulation_id:
                continue
            items.append(report)
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return items[:limit]

    @classmethod
    def append_log(
        cls,
        report: StoryReport,
        action: str,
        details: Dict[str, Any],
        chapter_no: Optional[int] = None,
        stage: str = "story",
    ) -> None:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "stage": stage,
            "section_index": chapter_no,
            "section_title": details.get("title"),
            "details": details,
        }
        report.logs.append(entry)
        report.logs = report.logs[-300:]
        cls._ensure_report_dir(report.report_id)
        with open(cls._get_agent_log_path(report.report_id), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @classmethod
    def get_agent_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        path = cls._get_agent_log_path(report_id)
        if not os.path.exists(path):
            return {"logs": [], "total_lines": 0, "from_line": from_line, "has_more": False}
        logs = []
        total_lines = 0
        with open(path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                total_lines = idx + 1
                if idx < from_line:
                    continue
                try:
                    logs.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
        return {"logs": logs, "total_lines": total_lines, "from_line": from_line, "has_more": False}


class StoryMVPService:
    TOPIC_COUNT = 3

    def __init__(self, simulation_id: str, project_id: str, graph_id: Optional[str], simulation_requirement: str):
        self.simulation_id = simulation_id
        self.project_id = project_id
        self.graph_id = graph_id
        self.simulation_requirement = simulation_requirement or "Write an engaging novel from the provided seed."
        self.llm = LLMClient()
        self.seed_text = (ProjectManager.get_extracted_text(project_id) or "")[:12000]

    def create_empty_report(self, report_id: Optional[str] = None) -> StoryReport:
        now = datetime.now().isoformat()
        return StoryReport(
            report_id=report_id or f"report_{uuid.uuid4().hex[:12]}",
            simulation_id=self.simulation_id,
            project_id=self.project_id,
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement,
            status=StoryStatus.PENDING,
            created_at=now,
            updated_at=now,
        )

    def generate_first_chapter(self, report: StoryReport) -> StoryReport:
        report.status = StoryStatus.GENERATING
        StoryReportManager.append_log(
            report,
            "report_start",
            {"message": "Story session started", "simulation_id": self.simulation_id},
        )
        report.story_bible = self._build_story_bible()
        report.title = report.story_bible.get("title") or "Untitled Story"
        report.premise = report.story_bible.get("premise") or self.simulation_requirement
        report.style = report.story_bible.get("style") or ""
        StoryReportManager.append_log(
            report,
            "planning_complete",
            {
                "message": "Story bible generated",
                "outline": report.to_dict()["outline"],
            },
        )
        chapter_payload = self._plan_chapter(
            chapter_no=1,
            report=report,
            selected_topic={
                "title": report.story_bible.get("opening_topic") or "Open with the core conflict",
                "summary": report.story_bible.get("opening_hook") or "Introduce the protagonist and the unstable world.",
            },
        )
        chapter = self._write_chapter(chapter_payload, chapter_no=1)
        report.chapters.append(chapter)
        report.topic_candidates = self._build_topic_candidates(chapter_payload.get("next_topics") or [])
        report.status = StoryStatus.WAITING_FOR_CHOICE
        self._finalize_report_after_chapter(report, chapter)
        return report

    def continue_with_topic(self, report: StoryReport, topic_id: str) -> StoryReport:
        selected = next((item for item in report.topic_candidates if item.topic_id == topic_id), None)
        if not selected:
            raise ValueError("Selected topic does not exist")
        report.selected_topics.append(selected.to_dict())
        report.status = StoryStatus.GENERATING
        next_no = len(report.chapters) + 1
        StoryReportManager.append_log(
            report,
            "topic_selected",
            {
                "message": f"Selected topic for chapter {next_no}",
                "topic": selected.to_dict(),
                "title": f"Chapter {next_no}",
            },
            chapter_no=next_no,
        )
        chapter_payload = self._plan_chapter(
            chapter_no=next_no,
            report=report,
            selected_topic=selected.to_dict(),
        )
        chapter = self._write_chapter(chapter_payload, chapter_no=next_no)
        report.chapters.append(chapter)
        report.topic_candidates = self._build_topic_candidates(chapter_payload.get("next_topics") or [])
        report.status = StoryStatus.WAITING_FOR_CHOICE
        self._finalize_report_after_chapter(report, chapter)
        return report

    def _finalize_report_after_chapter(self, report: StoryReport, chapter: StoryChapter) -> None:
        StoryReportManager.append_log(
            report,
            "section_complete",
            {
                "message": f"Chapter {chapter.chapter_no} complete",
                "content": f"## Chapter {chapter.chapter_no}: {chapter.title}\n\n{chapter.content}",
                "title": chapter.title,
                "summary": chapter.summary,
            },
            chapter_no=chapter.chapter_no,
        )
        StoryReportManager.append_log(
            report,
            "topics_ready",
            {
                "message": "Next chapter topics ready",
                "topics": [topic.to_dict() for topic in report.topic_candidates],
                "title": chapter.title,
            },
            chapter_no=chapter.chapter_no,
        )
        StoryReportManager.save_report(report)

    def _build_story_bible(self) -> Dict[str, Any]:
        system = (
            "You are a story bible generator for an interactive serialized novel. "
            "Return JSON only."
        )
        user = f"""
Seed requirement:
{self.simulation_requirement}

Source material excerpt:
{self.seed_text or "(No source text uploaded. Use the requirement as the primary seed.)"}

Return a JSON object with:
- title
- premise
- style
- opening_hook
- opening_topic
- protagonist
- setting
- key_conflict
- recurring_motifs (array of short strings)
"""
        try:
            data = self.llm.chat_json(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.5,
                max_tokens=1200,
            )
            return {
                "title": data.get("title") or "Interactive Story",
                "premise": data.get("premise") or self.simulation_requirement,
                "style": data.get("style") or "cinematic, character-driven prose",
                "opening_hook": data.get("opening_hook") or "A destabilizing event changes the protagonist's path.",
                "opening_topic": data.get("opening_topic") or "Begin with the seed conflict",
                "protagonist": data.get("protagonist") or {},
                "setting": data.get("setting") or {},
                "key_conflict": data.get("key_conflict") or "",
                "recurring_motifs": data.get("recurring_motifs") or [],
            }
        except Exception as exc:
            logger.warning("Build story bible failed, using fallback: %s", exc)
            return {
                "title": "Interactive Story",
                "premise": self.simulation_requirement,
                "style": "fast-paced, vivid, character-driven",
                "opening_hook": "A seemingly ordinary moment cracks open the hidden conflict.",
                "opening_topic": "Start from the inciting incident",
                "protagonist": {"name": "The protagonist"},
                "setting": {"name": "A volatile world"},
                "key_conflict": self.simulation_requirement,
                "recurring_motifs": ["choice", "secrets", "momentum"],
            }

    def _plan_chapter(self, chapter_no: int, report: StoryReport, selected_topic: Dict[str, Any]) -> Dict[str, Any]:
        chapter_summaries = [
            {
                "chapter_no": chapter.chapter_no,
                "title": chapter.title,
                "summary": chapter.summary,
            }
            for chapter in report.chapters[-3:]
        ]
        system = (
            "You are a chapter planner for an interactive novel. "
            "Return JSON only. Always produce exactly 3 next_topics."
        )
        user = f"""
Story title: {report.title}
Premise: {report.premise}
Style: {report.style}
Story bible: {json.dumps(report.story_bible, ensure_ascii=False)}
Previous chapters: {json.dumps(chapter_summaries, ensure_ascii=False)}
Current chapter number: {chapter_no}
Selected topic: {json.dumps(selected_topic, ensure_ascii=False)}

Return JSON with:
- chapter_title
- chapter_summary
- pov
- scene_beats (array of 4-6 short beats)
- chapter_goal
- chapter_hook
- next_topics: array of exactly 3 objects, each with title, summary, promise, focus_characters, tension_type
"""
        try:
            return self.llm.chat_json(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.6,
                max_tokens=1800,
            )
        except Exception as exc:
            logger.warning("Plan chapter failed, using fallback: %s", exc)
            base_title = selected_topic.get("title") or f"Chapter {chapter_no}"
            return {
                "chapter_title": base_title,
                "chapter_summary": selected_topic.get("summary") or "The story advances through conflict and discovery.",
                "pov": report.story_bible.get("protagonist", {}).get("name", "Protagonist"),
                "scene_beats": [
                    "Open on immediate fallout from the previous chapter.",
                    "Force the protagonist to pursue the selected topic.",
                    "Escalate pressure through an unexpected complication.",
                    "End on a hook that demands another choice.",
                ],
                "chapter_goal": selected_topic.get("summary") or "Advance the chosen thread.",
                "chapter_hook": "The choice opens a larger threat.",
                "next_topics": [
                    {
                        "title": "Push the main mystery forward",
                        "summary": "Follow the most urgent clue into new danger.",
                        "promise": "More answers, higher stakes.",
                        "focus_characters": [],
                        "tension_type": "mystery",
                    },
                    {
                        "title": "Force a character confrontation",
                        "summary": "Use the fallout to deepen the central relationship.",
                        "promise": "Sharper emotions and hidden motives.",
                        "focus_characters": [],
                        "tension_type": "relationship",
                    },
                    {
                        "title": "Let the outside world strike back",
                        "summary": "A new external disruption interrupts the current plan.",
                        "promise": "Bigger scale and fresh pressure.",
                        "focus_characters": [],
                        "tension_type": "action",
                    },
                ],
            }

    def _write_chapter(self, chapter_payload: Dict[str, Any], chapter_no: int) -> StoryChapter:
        system = (
            "You are a novelist writing one chapter of an interactive serialized story. "
            "Write vivid prose in markdown paragraphs. No bullet lists. No planning notes."
        )
        user = f"""
Story style: {chapter_payload.get('style') or 'character-driven and vivid'}
Chapter number: {chapter_no}
Chapter title: {chapter_payload.get('chapter_title')}
POV: {chapter_payload.get('pov')}
Chapter summary: {chapter_payload.get('chapter_summary')}
Goal: {chapter_payload.get('chapter_goal')}
Hook: {chapter_payload.get('chapter_hook')}
Scene beats: {json.dumps(chapter_payload.get('scene_beats') or [], ensure_ascii=False)}

Write a complete chapter of roughly 900-1400 Chinese characters.
Include scene progression, dialogue when useful, and end on a forward hook.
Start directly with the prose, without preamble.
"""
        content = self.llm.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.8,
            max_tokens=2200,
        ).strip()
        return StoryChapter(
            chapter_no=chapter_no,
            title=chapter_payload.get("chapter_title") or f"Chapter {chapter_no}",
            topic_title=chapter_payload.get("chapter_title") or f"Chapter {chapter_no}",
            topic_summary=chapter_payload.get("chapter_summary") or "",
            summary=chapter_payload.get("chapter_summary") or "",
            content=content,
            outcome={
                "pov": chapter_payload.get("pov"),
                "hook": chapter_payload.get("chapter_hook"),
                "goal": chapter_payload.get("chapter_goal"),
            },
        )

    def _build_topic_candidates(self, topics: List[Dict[str, Any]]) -> List[TopicCandidate]:
        items: List[TopicCandidate] = []
        for idx, item in enumerate(topics[: self.TOPIC_COUNT]):
            items.append(
                TopicCandidate(
                    topic_id=f"topic_{uuid.uuid4().hex[:8]}",
                    title=item.get("title") or f"Topic {idx + 1}",
                    summary=item.get("summary") or "",
                    promise=item.get("promise") or "",
                    focus_characters=item.get("focus_characters") or [],
                    tension_type=item.get("tension_type") or "",
                )
            )
        while len(items) < self.TOPIC_COUNT:
            n = len(items) + 1
            items.append(
                TopicCandidate(
                    topic_id=f"topic_{uuid.uuid4().hex[:8]}",
                    title=f"Topic {n}",
                    summary="Continue the story from a fresh angle.",
                )
            )
        return items
