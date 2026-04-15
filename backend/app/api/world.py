"""
世界模拟引擎 API
"""

import traceback
from flask import jsonify, request, send_file

from . import world_bp
from ..services.world_director import WorldNarrativeDirector
from ..services.world_engine import WorldEngine
from ..services.world_intro_director import WorldIntroDirector
from ..utils.logger import get_logger

logger = get_logger("mirofish.api.world")
engine = WorldEngine()
director = WorldNarrativeDirector()
intro_director = WorldIntroDirector()


@world_bp.route("/bootstrap", methods=["POST"])
def bootstrap_world():
    try:
        data = request.get_json() or {}
        simulation_id = data.get("simulation_id")
        if not simulation_id:
            return jsonify({"success": False, "error": "缺少 simulation_id"}), 400

        state = engine.bootstrap_world(
            simulation_id=simulation_id,
            force_rebuild=data.get("force_rebuild", False),
        )
        return jsonify({"success": True, "data": state.to_dict()})
    except Exception as exc:
        logger.error("初始化世界引擎失败: %s", exc)
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@world_bp.route("/<simulation_id>", methods=["GET"])
def get_world(simulation_id: str):
    try:
        state = engine.get_world(simulation_id)
        if not state:
            return jsonify({"success": False, "error": "世界状态不存在"}), 404
        return jsonify({"success": True, "data": state.to_dict()})
    except Exception as exc:
        logger.error("获取世界状态失败: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500


@world_bp.route("/<simulation_id>/claim", methods=["POST"])
def claim_character(simulation_id: str):
    try:
        data = request.get_json() or {}
        state = engine.claim_character(
            simulation_id=simulation_id,
            character_id=data.get("character_id", ""),
            player_name=data.get("player_name", "Player"),
        )
        return jsonify({"success": True, "data": state.to_dict()})
    except Exception as exc:
        logger.error("占用角色失败: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 400


@world_bp.route("/<simulation_id>/release", methods=["POST"])
def release_character(simulation_id: str):
    try:
        state = engine.release_character(simulation_id)
        return jsonify({"success": True, "data": state.to_dict()})
    except Exception as exc:
        logger.error("释放角色失败: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 400


@world_bp.route("/<simulation_id>/characters", methods=["POST"])
def add_character(simulation_id: str):
    try:
        data = request.get_json() or {}
        state = engine.add_character(
            simulation_id=simulation_id,
            name=data.get("name", ""),
            persona=data.get("persona", ""),
            summary=data.get("summary", ""),
            profession=data.get("profession", ""),
            current_location=data.get("current_location", ""),
            current_goal=data.get("current_goal", ""),
            appearance_notes=data.get("appearance_notes") or [],
        )
        return jsonify({"success": True, "data": state.to_dict()})
    except Exception as exc:
        logger.error("新增角色失败: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 400


@world_bp.route("/<simulation_id>/advance-time", methods=["POST"])
def advance_time(simulation_id: str):
    try:
        data = request.get_json() or {}
        amount = int(data.get("amount", 1))
        unit = data.get("unit", "day")
        state = engine.advance_time(
            simulation_id=simulation_id,
            amount=amount,
            unit=unit,
            narrative_instruction=data.get("narrative_instruction", ""),
        )
        return jsonify({"success": True, "data": state.to_dict()})
    except Exception as exc:
        logger.error("推进时间失败: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 400


@world_bp.route("/<simulation_id>/facts", methods=["POST"])
def add_fact(simulation_id: str):
    try:
        data = request.get_json() or {}
        state = engine.add_fact(
            simulation_id=simulation_id,
            scope=data.get("scope", "character"),
            subject=data.get("subject", ""),
            predicate=data.get("predicate", ""),
            object_value=data.get("object_value", ""),
            natural_language=data.get("natural_language", ""),
            effective_time=data.get("effective_time", "immediate"),
            duration=data.get("duration"),
            priority=int(data.get("priority", 5)),
            tags=data.get("tags") or [],
        )
        return jsonify({"success": True, "data": state.to_dict()})
    except Exception as exc:
        logger.error("注入 fact 失败: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 400


@world_bp.route("/<simulation_id>/image-tasks", methods=["GET"])
def list_image_tasks(simulation_id: str):
    try:
        tasks = engine.list_image_tasks(simulation_id)
        return jsonify({"success": True, "data": tasks})
    except Exception as exc:
        logger.error("获取图像任务失败: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 400


@world_bp.route("/<simulation_id>/image-tasks", methods=["POST"])
def create_image_task(simulation_id: str):
    try:
        data = request.get_json() or {}
        task = engine.create_image_task(
            simulation_id=simulation_id,
            character_id=data.get("character_id", ""),
            model=data.get("model"),
            style=data.get("style", "character-portrait"),
            prompt_override=data.get("prompt_override", ""),
            negative_prompt=data.get("negative_prompt", ""),
            auto_generate=data.get("auto_generate", True),
        )
        return jsonify({"success": True, "data": task.__dict__})
    except Exception as exc:
        logger.error("创建图像任务失败: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 400


@world_bp.route("/<simulation_id>/image-tasks/<task_id>/file", methods=["GET"])
def get_image_task_file(simulation_id: str, task_id: str):
    try:
        task = engine.get_image_task(simulation_id, task_id)
        if not task or not task.output_path:
            return jsonify({"success": False, "error": "图片文件不存在"}), 404
        return send_file(task.output_path)
    except Exception as exc:
        logger.error("读取图片任务文件失败: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 400


@world_bp.route("/<simulation_id>/dialogue", methods=["POST"])
def process_dialogue(simulation_id: str):
    try:
        data = request.get_json() or {}
        result = engine.process_dialogue(
            simulation_id=simulation_id,
            target_character_id=data.get("target_character_id", ""),
            message=data.get("message", ""),
        )
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        logger.error("处理人物对话失败: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 400


@world_bp.route("/<simulation_id>/director/node", methods=["POST"])
def build_director_node(simulation_id: str):
    try:
        data = request.get_json() or {}
        node = director.build_node(
            simulation_id=simulation_id,
            character_id=data.get("character_id", ""),
            target_character_id=data.get("target_character_id") or "",
            narrative_step=int(data.get("narrative_step", 0) or 0),
        )
        return jsonify({"success": True, "data": node})
    except Exception as exc:
        logger.error("生成剧情导演节点失败: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 400


@world_bp.route("/<simulation_id>/intro-plan", methods=["POST"])
def build_intro_plan(simulation_id: str):
    try:
        data = request.get_json() or {}
        result = intro_director.build_intro(
            simulation_id=simulation_id,
            character_id=data.get("character_id", ""),
        )
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        logger.error("生成角色引导脚本失败: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 400
