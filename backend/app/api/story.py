"""Story chapter session API."""

import os
import threading
import traceback
import uuid

from flask import jsonify, request, send_file

from . import story_bp
from ..models.project import ProjectManager
from ..models.task import TaskManager, TaskStatus
from ..services.simulation_manager import SimulationManager
from ..services.story_mvp import StoryMVPService, StoryReportManager, StoryStatus
from ..utils.logger import get_logger

logger = get_logger("mirofish.api.story_mvp")


def _resolve_story_context(simulation_id: str):
    manager = SimulationManager()
    simulation = manager.get_simulation(simulation_id)
    if not simulation:
        raise ValueError(f"Simulation not found: {simulation_id}")

    project = ProjectManager.get_project(simulation.project_id)
    if not project:
        raise ValueError(f"Project not found: {simulation.project_id}")

    graph_id = simulation.graph_id or project.graph_id
    requirement = project.simulation_requirement or "Write an interactive novel from the provided seed."
    return simulation, project, graph_id, requirement


@story_bp.route("/generate", methods=["POST"])
def create_story_session():
    try:
        data = request.get_json() or {}
        simulation_id = data.get("simulation_id")
        if not simulation_id:
            return jsonify({"success": False, "error": "Missing simulation_id"}), 400

        force_regenerate = bool(data.get("force_regenerate", False))
        existing_session = StoryReportManager.get_report_by_simulation(simulation_id)
        if existing_session and not force_regenerate:
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "report_id": existing_session.report_id,
                        "status": existing_session.status.value,
                        "already_generated": True,
                    },
                }
            )

        _, project, graph_id, requirement = _resolve_story_context(simulation_id)
        story_service = StoryMVPService(
            simulation_id=simulation_id,
            project_id=project.project_id,
            graph_id=graph_id,
            simulation_requirement=requirement,
        )
        story_session = story_service.create_empty_report(report_id=f"report_{uuid.uuid4().hex[:12]}")
        StoryReportManager.save_report(story_session)

        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="story_generate",
            metadata={"simulation_id": simulation_id, "report_id": story_session.report_id},
        )

        def run_initial_chapter():
            try:
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=10,
                    message="Generating story bible and chapter 1",
                )
                updated_session = story_service.generate_first_chapter(story_session)
                StoryReportManager.save_report(updated_session)
                task_manager.complete_task(
                    task_id,
                    {
                        "report_id": updated_session.report_id,
                        "simulation_id": simulation_id,
                        "status": updated_session.status.value,
                    },
                )
            except Exception as exc:
                logger.error("Initial story generation failed: %s", exc)
                story_session.status = StoryStatus.FAILED
                story_session.error = str(exc)
                StoryReportManager.save_report(story_session)
                task_manager.fail_task(task_id, str(exc))

        threading.Thread(target=run_initial_chapter, daemon=True).start()

        return jsonify(
            {
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "report_id": story_session.report_id,
                    "task_id": task_id,
                    "status": story_session.status.value,
                    "already_generated": False,
                },
            }
        )
    except Exception as exc:
        logger.error("Start story generation failed: %s", exc)
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@story_bp.route("/generate/status", methods=["POST"])
def get_story_session_status():
    try:
        data = request.get_json() or {}
        task_id = data.get("task_id")
        simulation_id = data.get("simulation_id")

        if simulation_id:
            existing_session = StoryReportManager.get_report_by_simulation(simulation_id)
            if existing_session and existing_session.status == StoryStatus.WAITING_FOR_CHOICE:
                return jsonify(
                    {
                        "success": True,
                        "data": {
                            "simulation_id": simulation_id,
                            "report_id": existing_session.report_id,
                            "status": existing_session.status.value,
                            "progress": 100,
                            "already_completed": True,
                        },
                    }
                )

        if not task_id:
            return jsonify({"success": False, "error": "Missing task_id or simulation_id"}), 400

        task = TaskManager().get_task(task_id)
        if not task:
            return jsonify({"success": False, "error": f"Task not found: {task_id}"}), 404
        return jsonify({"success": True, "data": task.to_dict()})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@story_bp.route("/<story_id>", methods=["GET"])
def get_story_session(story_id: str):
    story_session = StoryReportManager.get_report(story_id)
    if not story_session:
        return jsonify({"success": False, "error": f"Story session not found: {story_id}"}), 404
    return jsonify({"success": True, "data": story_session.to_dict()})


@story_bp.route("/by-simulation/<simulation_id>", methods=["GET"])
def get_story_session_by_simulation(simulation_id: str):
    story_session = StoryReportManager.get_report_by_simulation(simulation_id)
    if not story_session:
        return jsonify({"success": False, "error": f"No story found for {simulation_id}", "has_report": False}), 404
    return jsonify({"success": True, "data": story_session.to_dict(), "has_report": True})


@story_bp.route("/list", methods=["GET"])
def list_story_sessions():
    simulation_id = request.args.get("simulation_id")
    limit = request.args.get("limit", 50, type=int)
    sessions = StoryReportManager.list_reports(simulation_id=simulation_id, limit=limit)
    return jsonify({"success": True, "data": [item.to_dict() for item in sessions], "count": len(sessions)})


@story_bp.route("/<story_id>/choose-topic", methods=["POST"])
def select_next_topic(story_id: str):
    try:
        data = request.get_json() or {}
        topic_id = data.get("topic_id")
        if not topic_id:
            return jsonify({"success": False, "error": "Missing topic_id"}), 400

        story_session = StoryReportManager.get_report(story_id)
        if not story_session:
            return jsonify({"success": False, "error": f"Story session not found: {story_id}"}), 404
        if story_session.status == StoryStatus.GENERATING:
            return jsonify({"success": False, "error": "Story is still generating"}), 409

        story_session.status = StoryStatus.GENERATING
        story_session.topic_candidates = []
        story_session.error = None
        StoryReportManager.save_report(story_session)

        _, project, graph_id, requirement = _resolve_story_context(story_session.simulation_id)
        story_service = StoryMVPService(
            simulation_id=story_session.simulation_id,
            project_id=project.project_id,
            graph_id=graph_id,
            simulation_requirement=requirement,
        )

        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="story_continue",
            metadata={"report_id": story_session.report_id, "topic_id": topic_id},
        )

        def run_next_chapter():
            try:
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=10,
                    message="Generating next chapter from selected topic",
                )
                fresh_session = StoryReportManager.get_report(story_id)
                if not fresh_session:
                    raise ValueError(f"Story session not found: {story_id}")
                updated_session = story_service.continue_with_topic(fresh_session, topic_id)
                StoryReportManager.save_report(updated_session)
                task_manager.complete_task(
                    task_id,
                    {
                        "report_id": updated_session.report_id,
                        "status": updated_session.status.value,
                        "chapter_count": len(updated_session.chapters),
                    },
                )
            except Exception as exc:
                logger.error("Continue story failed: %s", exc)
                current_session = StoryReportManager.get_report(story_id)
                if current_session:
                    current_session.status = StoryStatus.FAILED
                    current_session.error = str(exc)
                    StoryReportManager.save_report(current_session)
                task_manager.fail_task(task_id, str(exc))

        threading.Thread(target=run_next_chapter, daemon=True).start()
        return jsonify(
            {
                "success": True,
                "data": {
                    "report_id": story_id,
                    "task_id": task_id,
                    "status": "generating",
                },
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@story_bp.route("/<story_id>/download", methods=["GET"])
def download_story_session(story_id: str):
    story_session = StoryReportManager.get_report(story_id)
    if not story_session:
        return jsonify({"success": False, "error": f"Story session not found: {story_id}"}), 404
    story_path = StoryReportManager._get_full_markdown_path(story_id)
    if not os.path.exists(story_path):
        return jsonify({"success": False, "error": "Story markdown not found"}), 404
    return send_file(story_path, as_attachment=True, download_name=f"{story_id}.md")


@story_bp.route("/<story_id>", methods=["DELETE"])
def delete_story_session(story_id: str):
    story_session = StoryReportManager.get_report(story_id)
    if not story_session:
        return jsonify({"success": False, "error": f"Story session not found: {story_id}"}), 404
    story_dir = StoryReportManager._get_report_dir(story_id)
    if os.path.isdir(story_dir):
        for root, dirs, files in os.walk(story_dir, topdown=False):
            for file_name in files:
                os.remove(os.path.join(root, file_name))
            for dir_name in dirs:
                os.rmdir(os.path.join(root, dir_name))
        os.rmdir(story_dir)
    return jsonify({"success": True, "message": f"Deleted: {story_id}"})


@story_bp.route("/chat", methods=["POST"])
def chat_with_story_guide():
    data = request.get_json() or {}
    simulation_id = data.get("simulation_id")
    message = (data.get("message") or "").strip()
    if not simulation_id or not message:
        return jsonify({"success": False, "error": "Missing simulation_id or message"}), 400

    story_session = StoryReportManager.get_report_by_simulation(simulation_id)
    if not story_session:
        return jsonify({"success": False, "error": "Story not found"}), 404

    latest_chapter = story_session.chapters[-1] if story_session.chapters else None
    response = "Story MVP mode is active. A full story guide agent is not wired in yet."
    if latest_chapter:
        response += f"\n\nLatest chapter \"{latest_chapter.title}\" summary: {latest_chapter.summary}"
    if story_session.topic_candidates:
        response += "\n\nAvailable next chapter topics:\n" + "\n".join(
            [f"- {item.title}: {item.summary}" for item in story_session.topic_candidates]
        )

    return jsonify({"success": True, "data": {"response": response, "tool_calls": [], "sources": []}})


@story_bp.route("/<story_id>/agent-log", methods=["GET"])
def get_story_log(story_id: str):
    from_line = request.args.get("from_line", 0, type=int)
    log_data = StoryReportManager.get_agent_log(story_id, from_line=from_line)
    return jsonify({"success": True, "data": log_data})


@story_bp.route("/<story_id>/console-log", methods=["GET"])
def get_story_console(story_id: str):
    from_line = request.args.get("from_line", 0, type=int)
    data = {"logs": [], "total_lines": 0, "from_line": from_line, "has_more": False}
    return jsonify({"success": True, "data": data})
