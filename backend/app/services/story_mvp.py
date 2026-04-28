"""
Story MVP service.

Flow:
1. Generate a blueprint and let the user confirm or regenerate it.
2. Extract initial ontology and relationships.
3. Bootstrap graph storage when available.
4. Generate one chapter at a time after blueprint confirmation.
"""

from __future__ import annotations

import copy
import glob
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
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
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
        focus_characters = data.get("focus_characters") or []
        if isinstance(focus_characters, str):
            focus_characters = [item.strip() for item in focus_characters.split(",") if item.strip()]
        if not isinstance(focus_characters, list):
            focus_characters = []
        return cls(
            topic_id=data["topic_id"],
            title=data.get("title", ""),
            summary=data.get("summary", ""),
            promise=data.get("promise", ""),
            focus_characters=focus_characters,
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
    plan: Dict[str, Any] = field(default_factory=dict)
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
            "plan": self.plan,
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
            plan=data.get("plan") or {},
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
    blueprint: Dict[str, Any] = field(default_factory=dict)
    outline_markdown: str = ""
    ontology: Dict[str, Any] = field(default_factory=dict)
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    graph_bootstrap: Dict[str, Any] = field(default_factory=dict)
    graph_committed_chapter_no: int = 0
    blueprint_user_notes: List[str] = field(default_factory=list)
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
            "blueprint": self.blueprint,
            "outline_markdown": self.outline_markdown,
            "ontology": self.ontology,
            "relationships": self.relationships,
            "graph_bootstrap": self.graph_bootstrap,
            "graph_committed_chapter_no": self.graph_committed_chapter_no,
            "blueprint_user_notes": self.blueprint_user_notes,
            "chapters": [c.to_dict() for c in self.chapters],
            "topic_candidates": [t.to_dict() for t in self.topic_candidates],
            "selected_topics": self.selected_topics,
            "latest_chapter": self.chapters[-1].to_dict() if self.chapters else None,
            "markdown_content": markdown,
            "outline": {
                "title": self.title or "互动故事",
                "summary": self.premise,
                "sections": [{"title": f"第{chapter.chapter_no}章：{chapter.title}"} for chapter in self.chapters],
            },
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoryReport":
        return cls(
            report_id=data["report_id"],
            simulation_id=data.get("simulation_id", ""),
            project_id=data.get("project_id", ""),
            graph_id=data.get("graph_id"),
            simulation_requirement=data.get("simulation_requirement", ""),
            status=StoryStatus(data.get("status", StoryStatus.PENDING.value)),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            title=data.get("title", ""),
            premise=data.get("premise", ""),
            style=data.get("style", ""),
            story_bible=data.get("story_bible") or {},
            blueprint=data.get("blueprint") or {},
            outline_markdown=data.get("outline_markdown", ""),
            ontology=data.get("ontology") or {},
            relationships=data.get("relationships") or [],
            graph_bootstrap=data.get("graph_bootstrap") or {},
            graph_committed_chapter_no=int(data.get("graph_committed_chapter_no") or 0),
            blueprint_user_notes=data.get("blueprint_user_notes") or [],
            chapters=[StoryChapter.from_dict(item) for item in data.get("chapters") or []],
            topic_candidates=[TopicCandidate.from_dict(item) for item in data.get("topic_candidates") or []],
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
    def _get_chapter_markdown_path(cls, report_id: str, chapter_no: int) -> str:
        return os.path.join(cls._get_report_dir(report_id), f"chapter_{chapter_no:02d}.md")

    @classmethod
    def _get_chapter_plan_path(cls, report_id: str, chapter_no: int) -> str:
        return os.path.join(cls._get_report_dir(report_id), f"chapter_{chapter_no:02d}_plan.json")

    @classmethod
    def _get_chapter_outcome_path(cls, report_id: str, chapter_no: int) -> str:
        return os.path.join(cls._get_report_dir(report_id), f"chapter_{chapter_no:02d}_outcome.json")

    @classmethod
    def _get_blueprint_path(cls, report_id: str) -> str:
        return os.path.join(cls._get_report_dir(report_id), "story_blueprint.json")

    @classmethod
    def _get_outline_path(cls, report_id: str) -> str:
        return os.path.join(cls._get_report_dir(report_id), "story_outline.md")

    @classmethod
    def _get_ontology_path(cls, report_id: str) -> str:
        return os.path.join(cls._get_report_dir(report_id), "ontology.json")

    @classmethod
    def _get_relationships_path(cls, report_id: str) -> str:
        return os.path.join(cls._get_report_dir(report_id), "relationships.json")

    @classmethod
    def _get_graph_bootstrap_path(cls, report_id: str) -> str:
        return os.path.join(cls._get_report_dir(report_id), "graph_bootstrap.json")

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
            report_dict = report.to_dict()
            cls._write_json(cls._get_meta_path(report.report_id), report_dict)
            cls._write_json(cls._get_blueprint_path(report.report_id), report.blueprint or {})
            cls._write_json(cls._get_ontology_path(report.report_id), report.ontology or {})
            cls._write_json(cls._get_relationships_path(report.report_id), report.relationships or [])
            cls._write_json(cls._get_graph_bootstrap_path(report.report_id), report.graph_bootstrap or {})
            cls._write_text(cls._get_full_markdown_path(report.report_id), report_dict["markdown_content"])
            cls._write_text(cls._get_outline_path(report.report_id), report.outline_markdown or "")

            active_paths = set()
            for chapter in report.chapters:
                chapter_path = cls._get_chapter_markdown_path(report.report_id, chapter.chapter_no)
                plan_path = cls._get_chapter_plan_path(report.report_id, chapter.chapter_no)
                outcome_path = cls._get_chapter_outcome_path(report.report_id, chapter.chapter_no)
                active_paths.update({os.path.normpath(chapter_path), os.path.normpath(plan_path), os.path.normpath(outcome_path)})
                cls._write_text(chapter_path, f"# 第{chapter.chapter_no}章：{chapter.title}\n\n{chapter.content}")
                cls._write_json(plan_path, chapter.plan or {})
                cls._write_json(outcome_path, chapter.outcome or {})

            for pattern in ("chapter_*.md", "chapter_*_plan.json", "chapter_*_outcome.json"):
                existing_paths = glob.glob(os.path.join(cls._get_report_dir(report.report_id), pattern))
                for existing_path in existing_paths:
                    if os.path.normpath(existing_path) not in active_paths:
                        os.remove(existing_path)

    @classmethod
    def _write_json(cls, path: str, data: Any) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def _write_text(cls, path: str, data: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(data or "")

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
        logs: List[Dict[str, Any]] = []
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
        self.simulation_requirement = simulation_requirement or "根据给定种子创作一部互动小说。"
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

    def generate_blueprint(self, report: StoryReport, user_instruction: str = "") -> StoryReport:
        report.status = StoryStatus.GENERATING
        report.error = None
        if user_instruction:
            report.blueprint_user_notes.append(user_instruction)
        StoryReportManager.append_log(
            report,
            "blueprint_start",
            {"message": "正在生成故事蓝图", "instruction": user_instruction},
        )

        blueprint = self._build_blueprint(user_instruction=user_instruction, current_blueprint=report.blueprint or None)
        report.blueprint = blueprint
        report.story_bible = blueprint
        report.title = blueprint.get("title") or "未命名故事"
        report.premise = blueprint.get("premise") or self.simulation_requirement
        report.style = blueprint.get("style") or ""
        report.outline_markdown = self._build_outline_markdown(blueprint)

        extraction = self._extract_ontology(blueprint)
        report.ontology = extraction.get("ontology") or {"entities": [], "world_rules": [], "timeline": []}
        report.relationships = extraction.get("relationships") or []
        report.graph_bootstrap = self._bootstrap_graph(report)

        StoryReportManager.append_log(
            report,
            "blueprint_ready",
            {
                "message": "蓝图已生成，等待确认",
                "title": report.title,
                "premise": report.premise,
                "graph_bootstrap": report.graph_bootstrap,
            },
        )
        report.status = StoryStatus.WAITING_FOR_CONFIRMATION
        StoryReportManager.save_report(report)
        return report

    def generate_first_chapter(self, report: StoryReport) -> StoryReport:
        if not report.blueprint:
            self.generate_blueprint(report)

        report.status = StoryStatus.GENERATING
        StoryReportManager.append_log(
            report,
            "chapter_start",
            {"message": "正在根据已确认蓝图生成第一章", "title": "第一章"},
            chapter_no=1,
        )
        opening_topic = {
            "title": report.blueprint.get("opening_topic") or "从核心冲突切入",
            "summary": report.blueprint.get("opening_hook") or "介绍主角、当前局势与即将失控的导火索。",
            "promise": "快速建立读者对世界、人物和冲突的兴趣。",
            "focus_characters": [self._get_protagonist_name(report)],
            "tension_type": "开场",
        }
        chapter_payload = self._plan_chapter(chapter_no=1, report=report, selected_topic=opening_topic)
        chapter = self._write_chapter(chapter_payload, chapter_no=1)
        report.chapters = [chapter]
        report.topic_candidates = self._build_topic_candidates(chapter_payload.get("next_topics") or [])
        report.status = StoryStatus.WAITING_FOR_CHOICE
        self._finalize_report_after_chapter(report, chapter)
        return report

    def continue_with_topic(self, report: StoryReport, topic_id: str) -> StoryReport:
        selected = next((item for item in report.topic_candidates if item.topic_id == topic_id), None)
        if not selected:
            raise ValueError("所选主题不存在")
        self._commit_pending_chapters(report)
        report.selected_topics.append(selected.to_dict())
        report.status = StoryStatus.GENERATING
        next_no = len(report.chapters) + 1
        StoryReportManager.append_log(
            report,
            "topic_selected",
            {"message": f"已为第{next_no}章选择分支主题", "topic": selected.to_dict(), "title": f"第{next_no}章"},
            chapter_no=next_no,
        )
        chapter_payload = self._plan_chapter(chapter_no=next_no, report=report, selected_topic=selected.to_dict())
        chapter = self._write_chapter(chapter_payload, chapter_no=next_no)
        report.chapters.append(chapter)
        report.topic_candidates = self._build_topic_candidates(chapter_payload.get("next_topics") or [])
        report.status = StoryStatus.WAITING_FOR_CHOICE
        self._finalize_report_after_chapter(report, chapter)
        return report

    def regenerate_current_chapter(self, report: StoryReport) -> StoryReport:
        if not report.chapters:
            return self.generate_first_chapter(report)

        current_chapter = report.chapters[-1]
        previous_chapters = list(report.chapters[:-1])
        if current_chapter.chapter_no == 1:
            selected_topic = {
                "title": report.blueprint.get("opening_topic") or "从核心冲突切入",
                "summary": report.blueprint.get("opening_hook") or "介绍主角、当前局势与即将失控的导火索。",
                "promise": "快速建立读者对世界、人物和冲突的兴趣。",
                "focus_characters": [self._get_protagonist_name(report)],
                "tension_type": "开场",
            }
        else:
            selected_topic = (report.selected_topics[-1] if report.selected_topics else None) or {
                "title": current_chapter.topic_title or current_chapter.title,
                "summary": current_chapter.topic_summary or current_chapter.summary,
                "promise": "",
                "focus_characters": [],
                "tension_type": "",
            }

        planning_report = copy.deepcopy(report)
        planning_report.chapters = previous_chapters

        report.status = StoryStatus.GENERATING
        StoryReportManager.append_log(
            report,
            "chapter_regenerate_start",
            {"message": f"Regenerating chapter {current_chapter.chapter_no}", "topic": selected_topic, "title": current_chapter.title},
            chapter_no=current_chapter.chapter_no,
        )
        chapter_payload = self._plan_chapter(
            chapter_no=current_chapter.chapter_no,
            report=planning_report,
            selected_topic=selected_topic,
        )
        chapter = self._write_chapter(chapter_payload, chapter_no=current_chapter.chapter_no)
        report.chapters[-1] = chapter
        report.topic_candidates = self._build_topic_candidates(chapter_payload.get("next_topics") or [])
        report.status = StoryStatus.WAITING_FOR_CHOICE
        self._finalize_report_after_chapter(report, chapter)
        return report

    def _finalize_report_after_chapter(self, report: StoryReport, chapter: StoryChapter) -> None:
        StoryReportManager.append_log(
            report,
            "section_complete",
            {
                "message": f"第{chapter.chapter_no}章已完成",
                "content": f"## 第{chapter.chapter_no}章：{chapter.title}\n\n{chapter.content}",
                "title": chapter.title,
                "summary": chapter.summary,
            },
            chapter_no=chapter.chapter_no,
        )
        StoryReportManager.append_log(
            report,
            "topics_ready",
            {
                "message": "下一章候选主题已生成",
                "topics": [topic.to_dict() for topic in report.topic_candidates],
                "title": chapter.title,
            },
            chapter_no=chapter.chapter_no,
        )
        StoryReportManager.save_report(report)

    def _commit_pending_chapters(self, report: StoryReport) -> None:
        pending_chapters = [
            chapter
            for chapter in report.chapters
            if chapter.chapter_no > (report.graph_committed_chapter_no or 0)
        ]
        if not pending_chapters:
            return
        for chapter in pending_chapters:
            self._commit_chapter_outcome_to_graph(report, chapter)
            report.graph_committed_chapter_no = chapter.chapter_no
            StoryReportManager.append_log(
                report,
                "chapter_graph_commit",
                {
                    "message": f"Committed chapter {chapter.chapter_no} outcome to graph context",
                    "title": chapter.title,
                    "graph_id": report.graph_id,
                },
                chapter_no=chapter.chapter_no,
            )
        StoryReportManager.save_report(report)

    def _commit_chapter_outcome_to_graph(self, report: StoryReport, chapter: StoryChapter) -> None:
        bootstrap = report.graph_bootstrap or {}
        provider = (bootstrap.get("provider") or Config.GRAPH_STORE_PROVIDER or "").lower()
        if provider != "neo4j":
            bootstrap["last_committed_chapter_no"] = chapter.chapter_no
            report.graph_bootstrap = bootstrap
            return
        if bootstrap.get("status") != "ready" or not report.graph_id:
            bootstrap["last_committed_chapter_no"] = chapter.chapter_no
            report.graph_bootstrap = bootstrap
            return

        from .graph_store_factory import create_graph_store

        store = create_graph_store()
        event_entity_id = f"chapter_event_{chapter.chapter_no:03d}"
        event_entity = {
            "entity_id": event_entity_id,
            "name": f"Chapter {chapter.chapter_no}: {chapter.title}",
            "entity_type": "Event",
            "description": chapter.outcome.get("summary") or chapter.summary or chapter.title,
            "status_summary": chapter.outcome.get("next_pressure") or chapter.summary or chapter.title,
            "aliases": [],
            "attributes": {
                "chapter_no": chapter.chapter_no,
                "chapter_title": chapter.title,
                "unresolved_questions": chapter.outcome.get("unresolved_questions") or [],
                "relationship_changes": chapter.outcome.get("relationship_changes") or [],
                "state_changes": chapter.outcome.get("state_changes") or [],
            },
            "appearance_count": 1,
            "importance_score": 1.0,
            "connected_core_count": 0,
            "state": "active",
        }
        store.upsert_entities(report.graph_id, [event_entity], chunk_index=chapter.chapter_no)

        participant_names = []
        pov = chapter.outcome.get("pov")
        if pov:
            participant_names.append(pov)
        topic_focus = ((chapter.plan or {}).get("selected_topic") or {}).get("focus_characters") or []
        if isinstance(topic_focus, str):
            topic_focus = [item.strip() for item in topic_focus.replace("、", ",").split(",") if item.strip()]
        participant_names.extend(topic_focus)
        relationships = []
        for name in dict.fromkeys([item for item in participant_names if item]):
            entity_id = self._find_entity_id_by_name(report, name)
            if not entity_id:
                continue
            relationships.append(
                {
                    "edge_uuid": f"{entity_id}_{event_entity_id}",
                    "source_entity_id": entity_id,
                    "target_entity_id": event_entity_id,
                    "relation_type": "INVOLVED_IN",
                    "description": f"{name} directly participated in chapter {chapter.chapter_no}.",
                    "evidence": chapter.outcome.get("summary") or chapter.summary or chapter.title,
                    "occurrence_count": 1,
                }
            )
        if relationships:
            store.upsert_relationships(report.graph_id, relationships, chunk_index=chapter.chapter_no)

        bootstrap["last_committed_chapter_no"] = chapter.chapter_no
        report.graph_bootstrap = bootstrap

    def _find_entity_id_by_name(self, report: StoryReport, name: str) -> Optional[str]:
        target = (name or "").strip().lower()
        if not target:
            return None
        for entity in report.ontology.get("entities") or []:
            entity_name = (entity.get("name") or "").strip().lower()
            aliases = [str(alias).strip().lower() for alias in (entity.get("aliases") or [])]
            if target == entity_name or target in aliases:
                return entity.get("entity_id")
        return None

    def _build_blueprint(self, user_instruction: str = "", current_blueprint: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        sanitized_blueprint = self._sanitize_blueprint_for_regeneration(current_blueprint)
        system = (
            "你是中文互动小说的蓝图设计师。"
            "你的目标不是做世界观堆砌，也不是输出网文提纲，而是把简短种子扩写成一个有人物命运牵扯、情感张力和持续悬念的故事蓝图。"
            "请优先塑造人物关系、欲望冲突、秘密、误解和代价。"
            "story_summary 必须写得像能吸引读者继续读下去的小说简介，而不是角色卡总结。"
            "请严格返回 JSON，不要输出解释、前言或代码块。"
        )
        user = f"""
故事种子：{self.simulation_requirement}

参考素材：
{self.seed_text or "无额外素材，请主要依据故事种子规划。"}

当前已有蓝图：{json.dumps(sanitized_blueprint or {}, ensure_ascii=False)}

额外改写指令：{user_instruction or "无"}

请返回一个 JSON 对象，字段必须包含：
- title：故事标题
- premise：一句话故事前提
- story_summary：一段 280 到 500 字的中文故事简介，要有文学感、张力和诱惑力
- style：文风说明
- theme：故事主题
- world_rules：世界规则数组
- protagonist：主角卡对象，至少包含 name / desire / flaw / secret
- core_conflict：核心冲突
- factions：主要势力数组
- major_characters：主要角色数组，每项至少包含 name / role / goal / conflict / summary
- long_term_mysteries：长线悬念数组
- opening_hook：第一章开场钩子
- opening_topic：第一章主题方向
- ending_direction：预期结局方向
- revision_notes：本次版本相对已有蓝图或用户指令的调整说明数组

要求：
1. story_summary 要突出“谁想要什么、谁阻碍谁、谁隐瞒了什么、谁将为此付出什么代价”。
2. 至少形成 2 到 3 组彼此牵制的人物关系。
3. 主角必须同时有外部困境和内部缺口。
4. opening_hook 要让人物关系立刻带电，不能只是介绍世界设定。
5. major_characters 里的 summary 要写出人物最危险或最迷人的一面。
6. 如果题材偏现实，请保持现实逻辑，不要强行奇幻化。
7. 不要预先把后续章节定死，只给出长线方向、人物矛盾和悬念。
8. 输出必须是合法 JSON。"""
        data = self.llm.chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.6,
            max_tokens=2600,
        )
        protagonist = data.get("protagonist") if isinstance(data.get("protagonist"), dict) else {}
        return {
            "title": data.get("title") or "互动故事",
            "premise": data.get("premise") or self.simulation_requirement,
            "story_summary": data.get("story_summary") or data.get("premise") or self.simulation_requirement,
            "style": data.get("style") or "人物驱动、情绪细腻、适合中文连载",
            "theme": data.get("theme") or "",
            "world_rules": data.get("world_rules") or [],
            "protagonist": protagonist,
            "core_conflict": data.get("core_conflict") or self.simulation_requirement,
            "factions": data.get("factions") or [],
            "major_characters": data.get("major_characters") or [],
            "long_term_mysteries": data.get("long_term_mysteries") or [],
            "opening_hook": data.get("opening_hook") or "平静表面被一道裂缝突然撕开。",
            "opening_topic": data.get("opening_topic") or "从核心冲突第一次显影的地方切入",
            "ending_direction": data.get("ending_direction") or "",
            "revision_notes": data.get("revision_notes") or ([user_instruction] if user_instruction else []),
        }

    def _sanitize_blueprint_for_regeneration(self, blueprint: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(blueprint, dict):
            return {}
        blocked_keys = {
            "chapter_outline",
            "outline_markdown",
            "markdown_content",
            "chapters",
            "topic_candidates",
            "selected_topics",
            "latest_chapter",
            "outline",
        }
        return {key: value for key, value in blueprint.items() if key not in blocked_keys}

    def _build_outline_markdown(self, blueprint: Dict[str, Any]) -> str:
        lines = [
            f"# {blueprint.get('title') or '故事蓝图'}",
            "",
            f"> {blueprint.get('premise') or ''}",
            "",
            "## 故事概述",
            "",
            blueprint.get("story_summary") or "",
            "",
            "## 核心设定",
            "",
            f"- 主题：{blueprint.get('theme') or ''}",
            f"- 文风：{blueprint.get('style') or ''}",
            f"- 核心冲突：{blueprint.get('core_conflict') or ''}",
            "",
            "## 长线方向",
            "",
        ]
        mysteries = blueprint.get("long_term_mysteries") or []
        if mysteries:
            lines.append("### 长线悬念")
            for item in mysteries:
                lines.append(f"- {item}")
            lines.append("")
        ending_direction = blueprint.get("ending_direction") or ""
        if ending_direction:
            lines.append("### 预期走向")
            lines.append(f"- {ending_direction}")
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def _extract_ontology(self, blueprint: Dict[str, Any]) -> Dict[str, Any]:
        system = (
            "你是小说蓝图到知识图谱的抽取器。"
            "请从故事蓝图里抽出足够支撑后续章节检索的初始实体和关系。"
            "重点不是百科式完备，而是把主角、关键角色、势力、核心秘密、目标和冲突先立起来。"
            "请严格返回 JSON，不要输出解释。"
        )
        user = f"""
故事蓝图：{json.dumps(blueprint, ensure_ascii=False)}

请返回 JSON，包含：
- ontology：对象，字段包括 entities / world_rules / timeline
- relationships：数组，每项包含 source_entity_id / target_entity_id / relation_type / description / evidence

entities 每项必须包含：
- entity_id
- name
- entity_type
- description
- aliases
- attributes
- status_summary

实体类型优先使用：Character / Organization / Location / Event / Asset / Secret / Goal / Conflict
关系类型优先使用：KNOWS / ALLIED_WITH / OPPOSES / HIDES / OWNS / LOCATED_IN / CAUSED_BY / WANTS / FEARS / SUSPECTS

要求：
1. 至少覆盖 protagonist、major_characters、factions、core_conflict、long_term_mysteries 里的关键项。
2. 如果蓝图里能明确人物目标或秘密，要抽成 Goal 或 Secret 实体，而不是只留在描述里。
3. 关系描述要可读，方便后续检索。
4. 输出必须是合法 JSON。"""
        data = self.llm.chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.35,
            max_tokens=2400,
        )
        ontology = data.get("ontology") if isinstance(data.get("ontology"), dict) else {}
        entities = ontology.get("entities") if isinstance(ontology.get("entities"), list) else []
        normalized_entities = []
        for idx, entity in enumerate(entities, start=1):
            if not isinstance(entity, dict):
                continue
            entity_name = entity.get("name") or f"Entity {idx}"
            normalized_entities.append(
                {
                    "entity_id": entity.get("entity_id") or f"entity_{idx:03d}",
                    "name": entity_name,
                    "entity_type": entity.get("entity_type") or "实体",
                    "description": entity.get("description") or entity_name,
                    "status_summary": entity.get("status_summary") or entity.get("description") or "",
                    "aliases": entity.get("aliases") or [],
                    "attributes": entity.get("attributes") or {},
                    "appearance_count": 1,
                    "importance_score": float(entity.get("importance_score", 1)),
                    "connected_core_count": int(entity.get("connected_core_count", 0)),
                    "state": "active",
                }
            )
        relationships = data.get("relationships") if isinstance(data.get("relationships"), list) else []
        normalized_relationships = []
        for idx, rel in enumerate(relationships, start=1):
            if not isinstance(rel, dict):
                continue
            normalized_relationships.append(
                {
                    "edge_uuid": rel.get("edge_uuid") or f"edge_{idx:03d}",
                    "source_entity_id": rel.get("source_entity_id"),
                    "target_entity_id": rel.get("target_entity_id"),
                    "relation_type": rel.get("relation_type") or "RELATED_TO",
                    "description": rel.get("description") or "",
                    "evidence": rel.get("evidence") or "蓝图初始化",
                    "occurrence_count": 1,
                }
            )
        return {
            "ontology": {
                "entities": normalized_entities,
                "world_rules": ontology.get("world_rules") or blueprint.get("world_rules") or [],
                "timeline": ontology.get("timeline") or [],
            },
            "relationships": [
                item
                for item in normalized_relationships
                if item.get("source_entity_id") and item.get("target_entity_id")
            ],
        }

    def _bootstrap_graph(self, report: StoryReport) -> Dict[str, Any]:
        snapshot = {
            "provider": (Config.GRAPH_STORE_PROVIDER or "none").lower(),
            "status": "skipped",
            "graph_id": report.graph_id,
            "entity_count": len(report.ontology.get("entities") or []),
            "relationship_count": len(report.relationships or []),
        }
        if snapshot["provider"] != "neo4j":
            return snapshot
        try:
            from .graph_store_factory import create_graph_store

            store = create_graph_store()
            graph_id = report.graph_id or store.create_graph(report.title or "故事图谱", report.premise or "")
            report.graph_id = graph_id
            entities = report.ontology.get("entities") or []
            relationships = report.relationships or []
            if entities:
                store.upsert_entities(graph_id, entities, chunk_index=0)
            if relationships:
                store.upsert_relationships(graph_id, relationships, chunk_index=0)
            self._persist_project_graph_id(graph_id)
            graph_data = store.get_graph_data(graph_id)
            snapshot.update(
                {
                    "status": "ready",
                    "graph_id": graph_id,
                    "node_count": graph_data.get("node_count", 0),
                    "edge_count": graph_data.get("edge_count", 0),
                }
            )
        except Exception as exc:
            logger.warning("Bootstrap graph failed: %s", exc)
            snapshot.update({"status": "failed", "error": str(exc)})
        return snapshot

    def _persist_project_graph_id(self, graph_id: str) -> None:
        project = ProjectManager.get_project(self.project_id)
        if not project:
            return
        project.graph_id = graph_id
        ProjectManager.save_project(project)

    def _build_graph_context(self, report: StoryReport) -> Dict[str, Any]:
        entity_summaries = []
        for entity in (report.ontology.get("entities") or [])[:12]:
            entity_summaries.append(
                {
                    "name": entity.get("name"),
                    "type": entity.get("entity_type"),
                    "summary": entity.get("status_summary") or entity.get("description"),
                }
            )
        relationship_summaries = []
        for rel in report.relationships[:12]:
            relationship_summaries.append(
                {
                    "source": rel.get("source_entity_id"),
                    "target": rel.get("target_entity_id"),
                    "type": rel.get("relation_type"),
                    "description": rel.get("description"),
                }
            )
        return {
            "entities": entity_summaries,
            "relationships": relationship_summaries,
            "graph_bootstrap": report.graph_bootstrap,
        }

    def _resolve_entity_id_from_name(self, report: StoryReport, name: str) -> Optional[str]:
        target = (name or "").strip().lower()
        if not target:
            return None
        for entity in report.ontology.get("entities") or []:
            entity_name = (entity.get("name") or "").strip().lower()
            aliases = [str(alias).strip().lower() for alias in (entity.get("aliases") or [])]
            if target == entity_name or target in aliases:
                return entity.get("entity_id")
        return None

    def _extract_memory_queries(self, report: StoryReport, selected_topic: Dict[str, Any]) -> List[str]:
        queries: List[str] = []
        for value in [
            selected_topic.get("title"),
            selected_topic.get("summary"),
            selected_topic.get("promise"),
            report.blueprint.get("core_conflict"),
        ]:
            text = (value or "").strip()
            if text:
                queries.append(text)
        last_outcome = report.chapters[-1].outcome if report.chapters else {}
        for question in last_outcome.get("unresolved_questions") or []:
            text = str(question).strip()
            if text:
                queries.append(text)
        next_pressure = (last_outcome.get("next_pressure") or "").strip()
        if next_pressure:
            queries.append(next_pressure)

        compact_queries: List[str] = []
        seen = set()
        for query in queries:
            cleaned = " ".join(str(query).split())
            if not cleaned:
                continue
            cleaned = cleaned[:80]
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            compact_queries.append(cleaned)
        return compact_queries[:6]

    def _compose_memory_text(self, memory: Dict[str, Any]) -> str:
        lines = ["相关记忆"]
        if memory.get("relevant_entities"):
            lines.append("相关角色与实体：")
            for entity in memory["relevant_entities"][:6]:
                lines.append(f"- {entity.get('name')} ({entity.get('type')}): {entity.get('summary')}")
        if memory.get("relationship_lines"):
            lines.append("相关关系：")
            for line in memory["relationship_lines"][:8]:
                lines.append(f"- {line}")
        if memory.get("facts"):
            lines.append("相关事实：")
            for fact in memory["facts"][:10]:
                lines.append(f"- {fact}")
        if memory.get("open_threads"):
            lines.append("未解决线索：")
            for thread in memory["open_threads"][:6]:
                lines.append(f"- {thread}")
        return "\n".join(lines)

    def _retrieve_story_memory(self, report: StoryReport, selected_topic: Dict[str, Any]) -> Dict[str, Any]:
        fallback = {
            "facts": [],
            "relevant_entities": [],
            "relationship_lines": [],
            "open_threads": [],
            "queries": [],
            "memory_text": "",
        }
        bootstrap = report.graph_bootstrap or {}
        if (bootstrap.get("provider") or "").lower() != "neo4j":
            return fallback
        if bootstrap.get("status") != "ready" or not report.graph_id:
            return fallback

        queries = self._extract_memory_queries(report, selected_topic)
        focus_names: List[str] = []
        focus_characters = selected_topic.get("focus_characters") or []
        if isinstance(focus_characters, str):
            focus_characters = [item.strip() for item in focus_characters.replace("、", ",").split(",") if item.strip()]
        if isinstance(focus_characters, list):
            focus_names.extend([str(item).strip() for item in focus_characters if str(item).strip()])
        last_outcome = report.chapters[-1].outcome if report.chapters else {}
        pov = (last_outcome.get("pov") or "").strip()
        if pov:
            focus_names.append(pov)
        protagonist_name = self._get_protagonist_name(report)
        if protagonist_name:
            focus_names.append(protagonist_name)

        facts: List[str] = []
        entity_summaries: List[Dict[str, Any]] = []
        relationship_lines: List[str] = []
        open_threads = [str(item).strip() for item in (last_outcome.get("unresolved_questions") or []) if str(item).strip()]

        try:
            from .graph_store_factory import create_graph_store

            store = create_graph_store()
            for query in queries:
                facts.extend(store.search_facts(report.graph_id, query, limit=6))

            seen_entity_ids = set()
            for name in focus_names:
                entity_id = self._resolve_entity_id_from_name(report, name)
                if not entity_id or entity_id in seen_entity_ids:
                    continue
                seen_entity_ids.add(entity_id)
                snapshot = store.get_entity_snapshot(report.graph_id, entity_id)
                if not snapshot:
                    continue
                labels = snapshot.get("labels") or ["Entity"]
                entity_type = next((label for label in labels if label not in ["Entity", "Node"]), "实体")
                entity_summaries.append(
                    {
                        "entity_id": entity_id,
                        "name": snapshot.get("name") or name,
                        "type": entity_type,
                        "summary": snapshot.get("summary") or "",
                    }
                )
                for neighbor in (snapshot.get("related_nodes") or [])[:6]:
                    rel = neighbor.get("relationship") or {}
                    relationship_lines.append(
                        f"{snapshot.get('name') or name} --[{rel.get('type') or '相关'}]--> {neighbor.get('name')}: {rel.get('description') or neighbor.get('summary') or ''}"
                    )
        except Exception as exc:
            logger.warning("Retrieve story memory failed, using fallback graph context: %s", exc)
            return fallback

        deduped_facts: List[str] = []
        seen_facts = set()
        for fact in facts:
            normalized = " ".join(str(fact).split())
            if not normalized or normalized in seen_facts:
                continue
            seen_facts.add(normalized)
            deduped_facts.append(normalized)

        deduped_relationships: List[str] = []
        seen_relationships = set()
        for line in relationship_lines:
            normalized = " ".join(str(line).split())
            if not normalized or normalized in seen_relationships:
                continue
            seen_relationships.add(normalized)
            deduped_relationships.append(normalized)

        memory = {
            "facts": deduped_facts[:12],
            "relevant_entities": entity_summaries[:6],
            "relationship_lines": deduped_relationships[:10],
            "open_threads": open_threads[:6],
            "queries": queries,
        }
        memory["memory_text"] = self._compose_memory_text(memory)
        return memory

    def _plan_chapter(self, chapter_no: int, report: StoryReport, selected_topic: Dict[str, Any]) -> Dict[str, Any]:
        chapter_summaries = [
            {"chapter_no": chapter.chapter_no, "title": chapter.title, "summary": chapter.summary}
            for chapter in report.chapters[-3:]
        ]
        graph_context = self._build_graph_context(report)
        story_memory = self._retrieve_story_memory(report, selected_topic)
        system = (
            "你是互动小说的章节导演，不是流水账提纲生成器。"
            "请根据已确认的故事蓝图、图谱上下文、检索到的相关记忆、最近章节摘要和用户选中的方向，"
            "规划出一章有情绪起伏、关系拉扯和可写性的小说章节。"
            "你输出的是给小说作者使用的章节计划，因此必须强调场景、隐性冲突、人物欲望和意象，而不是机械事件清单。"
            "请严格只返回 JSON，不要输出解释。next_topics 必须严格返回 3 个。"
        )
        user = f"""
故事标题：{report.title}
故事前提：{report.premise}
故事概述：{report.blueprint.get("story_summary") or ""}
文风：{report.style}
整体蓝图：{json.dumps(report.blueprint, ensure_ascii=False)}
图谱上下文：{json.dumps(graph_context, ensure_ascii=False)}
检索到的记忆摘要：{story_memory.get('memory_text', '')}
检索查询词：{json.dumps(story_memory.get('queries') or [], ensure_ascii=False)}
最近章节摘要：{json.dumps(chapter_summaries, ensure_ascii=False)}
当前章节编号：{chapter_no}
用户选中的下一章方向：{json.dumps(selected_topic, ensure_ascii=False)}

请返回 JSON，字段必须包含：
- chapter_title：本章标题
- chapter_summary：本章摘要，写成像编辑部用的章节梗概，不要像流水账
- pov：本章主要视角人物
- emotional_tone：本章情绪底色
- relational_tension：本章最核心的人物关系拉扯
- hidden_pressure：本章不能被角色直接说出口的压力或秘密
- imagery_motifs：本章可反复出现的意象或视觉线索，数组
- chapter_goal：本章要推进到哪里
- chapter_hook：本章结尾留下的钩子
- scene_beats：数组，每项至少包含 beat_title / beat_goal / tension / subtext / visible_action / imagery
- next_topics：固定 3 项，每项包含 title / summary / promise / focus_characters / tension_type

要求：
1. 规划必须严格延续蓝图和已有章节。
2. 不要把 scene_beats 写成“先A再B再C”的空洞提纲，要让每个 beat 都能被直接写成场景。
3. 每个 beat 至少要有一个人物欲望冲突或信息不对称。
4. next_topics 必须明显区分为不同走向，不能只是同义改写。
5. 输出必须是合法 JSON。"""
        payload = self.llm.chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.6,
            max_tokens=2400,
        )
        payload["style"] = report.style
        payload["selected_topic"] = selected_topic
        payload["graph_context"] = graph_context
        payload["story_memory"] = story_memory
        payload["scene_reactions"] = self._simulate_scene_reactions(report=report, chapter_payload=payload)
        return payload

    def _select_scene_characters(self, report: StoryReport, chapter_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        selected_topic = chapter_payload.get("selected_topic") or {}
        requested_names: List[str] = []
        pov = (chapter_payload.get("pov") or "").strip()
        if pov:
            requested_names.append(pov)
        focus = selected_topic.get("focus_characters") or []
        if isinstance(focus, str):
            focus = [item.strip() for item in focus.split(",") if item.strip()]
        if isinstance(focus, list):
            requested_names.extend([str(item).strip() for item in focus if str(item).strip()])
        protagonist = self._get_protagonist_name(report)
        if protagonist:
            requested_names.append(protagonist)

        registry: List[Dict[str, Any]] = []
        seen = set()
        for name in requested_names:
            target = name.strip().lower()
            if not target:
                continue
            for character in report.blueprint.get("major_characters") or []:
                char_name = str(character.get("name") or "").strip()
                if not char_name:
                    continue
                aliases = [str(alias).strip().lower() for alias in (character.get("aliases") or [])]
                if target == char_name.lower() or target in aliases:
                    normalized_name = char_name.lower()
                    if normalized_name in seen:
                        break
                    seen.add(normalized_name)
                    registry.append(
                        {
                            "name": char_name,
                            "role": character.get("role") or "",
                            "goal": character.get("goal") or "",
                            "conflict": character.get("conflict") or "",
                            "summary": character.get("summary") or character.get("description") or "",
                        }
                    )
                    break

        if not registry:
            for character in (report.blueprint.get("major_characters") or [])[:3]:
                char_name = str(character.get("name") or "").strip()
                if not char_name:
                    continue
                registry.append(
                    {
                        "name": char_name,
                        "role": character.get("role") or "",
                        "goal": character.get("goal") or "",
                        "conflict": character.get("conflict") or "",
                        "summary": character.get("summary") or character.get("description") or "",
                    }
                )

        return registry[:3]

    def _simulate_scene_reactions(self, report: StoryReport, chapter_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        characters = self._select_scene_characters(report, chapter_payload)
        if not characters:
            return []

        recent_chapters = [
            {"chapter_no": chapter.chapter_no, "title": chapter.title, "summary": chapter.summary}
            for chapter in report.chapters[-2:]
        ]
        system = (
            "你是互动小说里的轻量角色反应模拟器。"
            "你不负责写正文，只负责推断关键角色在本章开始前和本章推进中会如何表态、隐瞒、误解和行动。"
            "请让每个角色都像一个具体的人，而不是设定卡。"
            "严格只返回 JSON。"
        )
        user = f"""
故事标题：{report.title}
故事概述：{report.blueprint.get("story_summary") or ""}
核心冲突：{report.blueprint.get("core_conflict") or ""}
本章规划：{json.dumps(chapter_payload, ensure_ascii=False)}
最近章节：{json.dumps(recent_chapters, ensure_ascii=False)}
图谱记忆：{chapter_payload.get('story_memory', {}).get('memory_text', '')}
关键角色：{json.dumps(characters, ensure_ascii=False)}

请返回 JSON，对象中包含 reactions 数组。每个 reaction 必须包含：
- character
- public_response：角色表面会怎么说、怎么做
- private_intent：角色真实想要什么
- emotional_state：角色此刻主要情绪
- misunderstanding：角色此刻的误解或偏见
- secret_pressure：角色最不愿说出的压力
- likely_action：如果局势继续推进，角色最可能采取的动作
- sensory_signal：一个能表现角色状态的可见细节

要求：
1. 角色之间的反应必须彼此牵连，不能各说各话。
2. public_response 和 private_intent 必须有落差。
3. 用中文，内容要具体，不要抽象概括。
4. 输出必须是合法 JSON。"""
        try:
            data = self.llm.chat_json(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.7,
                max_tokens=1800,
            )
            reactions = data.get("reactions") if isinstance(data.get("reactions"), list) else []
        except Exception as exc:
            logger.warning("Simulate scene reactions failed, using fallback: %s", exc)
            reactions = []

        normalized: List[Dict[str, Any]] = []
        for character in characters:
            name = character.get("name") or "角色"
            matched = next(
                (
                    item for item in reactions
                    if isinstance(item, dict) and str(item.get("character") or "").strip() == name
                ),
                None,
            )
            normalized.append(
                {
                    "character": name,
                    "role": character.get("role") or "",
                    "public_response": (matched or {}).get("public_response") or f"{name}会尽量维持表面镇定，但言行里带出压抑和防备。",
                    "private_intent": (matched or {}).get("private_intent") or character.get("goal") or f"{name}想让局势朝对自己有利的方向发展。",
                    "emotional_state": (matched or {}).get("emotional_state") or "压抑而紧绷",
                    "misunderstanding": (matched or {}).get("misunderstanding") or character.get("conflict") or "暂时还看不清对方真正的意图。",
                    "secret_pressure": (matched or {}).get("secret_pressure") or "一旦把真实处境说出口，关系就会立刻失衡。",
                    "likely_action": (matched or {}).get("likely_action") or f"{name}会在试探中寻找下一步主动权。",
                    "sensory_signal": (matched or {}).get("sensory_signal") or "指尖微微收紧，像在克制某种冲动。",
                }
            )
        return normalized


    def _write_chapter(self, chapter_payload: Dict[str, Any], chapter_no: int) -> StoryChapter:
        system = (
            "你是一名中文长篇连载小说作者。"
            "你要把章节计划和角色反应写成真正可读的小说正文，而不是剧情解释。"
            "只输出正文，不要输出提纲、注释、解释、标题说明或额外提示。"
        )
        user = f"""
文风：{chapter_payload.get('style') or '人物驱动、场景鲜明、适合中文连载'}
章节编号：{chapter_no}
章节标题：{chapter_payload.get('chapter_title')}
视角人物：{chapter_payload.get('pov')}
章节摘要：{chapter_payload.get('chapter_summary')}
章节目标：{chapter_payload.get('chapter_goal')}
章节结尾钩子：{chapter_payload.get('chapter_hook')}
本章情绪底色：{chapter_payload.get('emotional_tone') or ''}
本章关系张力：{chapter_payload.get('relational_tension') or ''}
不能明说的压力：{chapter_payload.get('hidden_pressure') or ''}
意象线索：{json.dumps(chapter_payload.get('imagery_motifs') or [], ensure_ascii=False)}
场景节拍：{json.dumps(chapter_payload.get('scene_beats') or [], ensure_ascii=False)}
关键角色反应：{json.dumps(chapter_payload.get('scene_reactions') or [], ensure_ascii=False)}
图谱记忆：{chapter_payload.get('story_memory', {}).get('memory_text', '')}

请写出一章完整的中文小说正文，要求：
1. 长度控制在 1200 到 2200 字。
2. 你写的是小说正文，不是剧情简介，不是角色说明，不是提纲扩写。
3. 优先通过动作、表情、语气、停顿、环境、触感、光线、声音来表现人物情绪，不要频繁直接解释“他很痛苦”“她很愤怒”。
4. 对话要带潜台词，人物表面说的话和真实意图可以不一致。
5. 至少写出一到两个能让人记住的场景细节或意象。
6. 严禁总结腔、解释腔、任务腔，禁止用“这一章里”“此时此刻故事推进到”之类说法。
7. 结尾必须留下自然但有牵引力的钩子。"""
        content = self.llm.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.8,
            max_tokens=3200,
        ).strip()
        outcome = self._extract_chapter_outcome(chapter_payload=chapter_payload, content=content, chapter_no=chapter_no)
        return StoryChapter(
            chapter_no=chapter_no,
            title=chapter_payload.get("chapter_title") or f"第{chapter_no}章",
            topic_title=(chapter_payload.get("selected_topic") or {}).get("title") or chapter_payload.get("chapter_title") or f"第{chapter_no}章",
            topic_summary=(chapter_payload.get("selected_topic") or {}).get("summary") or chapter_payload.get("chapter_summary") or "",
            summary=chapter_payload.get("chapter_summary") or "",
            content=content,
            plan=chapter_payload,
            outcome=outcome,
        )


    def _extract_chapter_outcome(self, chapter_payload: Dict[str, Any], content: str, chapter_no: int) -> Dict[str, Any]:
        system = (
            "你是章节结果抽取器。"
            "请根据章节正文提取后续生成真正需要的结构化结果。"
            "不要复述文学描写，只抽取状态变化、关系变化、秘密、悬念和下一章压力。"
            "只返回 JSON，不要输出解释。"
        )
        user = f"""
章节编号：{chapter_no}
章节规划：{json.dumps(chapter_payload, ensure_ascii=False)}
章节正文：{content}

请返回 JSON，字段包括：
- summary：用 80 到 160 字概括本章实际发生了什么
- state_changes：人物处境、位置、伤势、目标变化
- relationship_changes：谁与谁更靠近、疏离、猜疑、对立
- new_secrets：本章新增或暴露出的秘密
- unresolved_questions：本章结束时仍悬而未决的问题
- next_pressure：会直接压到下一章开头的外部或内部压力

要求：
1. 尽量具体，优先写可供下一章使用的信息。
2. 不要写成空泛总结。
3. 输出必须是合法 JSON。"""
        try:
            data = self.llm.chat_json(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.3,
                max_tokens=1400,
            )
            return {
                "summary": data.get("summary") or chapter_payload.get("chapter_summary") or "",
                "state_changes": data.get("state_changes") or [],
                "relationship_changes": data.get("relationship_changes") or [],
                "new_secrets": data.get("new_secrets") or [],
                "unresolved_questions": data.get("unresolved_questions") or [],
                "next_pressure": data.get("next_pressure") or chapter_payload.get("chapter_hook") or "",
                "pov": chapter_payload.get("pov"),
                "goal": chapter_payload.get("chapter_goal"),
                "hook": chapter_payload.get("chapter_hook"),
            }
        except Exception as exc:
            logger.warning("Extract chapter outcome failed, using fallback: %s", exc)
            return {
                "summary": chapter_payload.get("chapter_summary") or "",
                "state_changes": [],
                "relationship_changes": [],
                "new_secrets": [],
                "unresolved_questions": [],
                "next_pressure": chapter_payload.get("chapter_hook") or "",
                "pov": chapter_payload.get("pov"),
                "goal": chapter_payload.get("chapter_goal"),
                "hook": chapter_payload.get("chapter_hook"),
            }


    def _build_topic_candidates(self, topics: List[Dict[str, Any]]) -> List[TopicCandidate]:
        items: List[TopicCandidate] = []
        for idx, item in enumerate(topics[: self.TOPIC_COUNT]):
            focus_characters = item.get("focus_characters") or []
            if isinstance(focus_characters, str):
                focus_characters = [piece.strip() for piece in focus_characters.replace("、", ",").split(",") if piece.strip()]
            elif not isinstance(focus_characters, list):
                focus_characters = []
            items.append(
                TopicCandidate(
                    topic_id=f"topic_{uuid.uuid4().hex[:8]}",
                    title=item.get("title") or f"主题{idx + 1}",
                    summary=item.get("summary") or "",
                    promise=item.get("promise") or "",
                    focus_characters=focus_characters,
                    tension_type=item.get("tension_type") or "",
                )
            )
        while len(items) < self.TOPIC_COUNT:
            n = len(items) + 1
            items.append(
                TopicCandidate(
                    topic_id=f"topic_{uuid.uuid4().hex[:8]}",
                    title=f"主题{n}",
                    summary="从新的角度继续推进故事。",
                )
            )
        return items

    def _get_protagonist_name(self, report: StoryReport) -> str:
        return (
            report.blueprint.get("protagonist", {}).get("name")
            or report.story_bible.get("protagonist", {}).get("name")
            or "主角"
        )
