"""故事 API：/api/story/*"""

import io
import os

from flask import jsonify, request, send_file

from ..config import Config
from ..story import service, store, styles
from ..story.models import StoryStatus
from ..utils.file_parser import FileParser
from ..utils.logger import get_logger
from . import story_bp

logger = get_logger("story.api")


def ok(data=None, status=200):
    return jsonify({"success": True, "data": data}), status


def fail(message, status=400):
    return jsonify({"success": False, "error": message}), status


@story_bp.errorhandler(service.Busy)
def _busy(exc):
    return fail(str(exc), 409)


@story_bp.errorhandler(KeyError)
def _missing(exc):
    return fail(f"故事不存在: {exc}", 404)


@story_bp.errorhandler(ValueError)
def _bad(exc):
    return fail(str(exc), 400)


@story_bp.errorhandler(Exception)
def _unexpected(exc):
    logger.exception("接口异常")
    return fail(str(exc), 500)


def _session_or_404(story_id):
    session = store.load(story_id)
    if not session:
        raise KeyError(story_id)
    return session


@story_bp.route("", methods=["POST"])
def create_story():
    """multipart：seed + files[]；或 JSON：{seed}"""
    if request.content_type and request.content_type.startswith("multipart/"):
        seed = request.form.get("seed", "")
        style_id, style_notes = request.form.get("style", ""), request.form.get("style_notes", "")
        texts, names = [], []
        upload_dir = os.path.join(Config.UPLOAD_FOLDER, "tmp")
        os.makedirs(upload_dir, exist_ok=True)
        for f in request.files.getlist("files"):
            ext = os.path.splitext(f.filename or "")[1].lower().lstrip(".")
            if ext not in Config.ALLOWED_EXTENSIONS:
                return fail(f"不支持的文件类型: {f.filename}")
            path = os.path.join(upload_dir, f"{os.urandom(6).hex()}.{ext}")
            f.save(path)
            try:
                texts.append(FileParser.extract_text(path))
                names.append(f.filename)
            finally:
                os.remove(path)
        source_text, source_name = "\n\n".join(texts), "、".join(names)
    else:
        data = request.get_json() or {}
        seed, source_text, source_name = data.get("seed", ""), data.get("source_text", ""), ""
        style_id, style_notes = data.get("style", ""), data.get("style_notes", "")
    if not seed.strip() and not source_text.strip():
        return fail("请填写故事需求或上传素材")
    session = service.create_session(seed, source_text, source_name, style_id, style_notes)
    return ok({"id": session.id}, 201)


@story_bp.route("/styles", methods=["GET"])
def list_styles():
    return ok(styles.list_styles())


@story_bp.route("/<story_id>/style", methods=["POST"])
def set_style(story_id):
    data = request.get_json() or {}
    return ok(service.set_style(story_id, data.get("style", ""), data.get("style_notes", "")).public_dict())


@story_bp.route("/list", methods=["GET"])
def list_stories():
    limit = request.args.get("limit", 50, type=int)
    return ok([s.list_item() for s in store.list_all(limit)])


@story_bp.route("/<story_id>", methods=["GET"])
def get_story(story_id):
    return ok(_session_or_404(story_id).public_dict())


@story_bp.route("/<story_id>", methods=["DELETE"])
def delete_story(story_id):
    session = _session_or_404(story_id)
    if session.status == StoryStatus.GENERATING:
        raise service.Busy("生成中的故事不能删除")
    store.delete(story_id)
    return ok()


@story_bp.route("/<story_id>/timeline", methods=["GET"])
def get_timeline(story_id):
    """完整事件时间线（幕后视图）。"""
    session = _session_or_404(story_id)
    world = session.world
    if not world:
        return ok([])
    return ok([{**e.model_dump(mode="json"), "actor_name": world.char_name(e.actor)} for e in world.timeline])


@story_bp.route("/<story_id>/blueprint/regenerate", methods=["POST"])
def regenerate_blueprint(story_id):
    session = _session_or_404(story_id)
    if session.chapters:
        raise ValueError("已经开始写章节，不能再修改蓝图")
    instruction = ((request.get_json() or {}).get("instruction") or "").strip()
    return ok(service.start_job(story_id, "blueprint", {"instruction": instruction}).public_dict())


@story_bp.route("/<story_id>/blueprint/confirm", methods=["POST"])
def confirm_blueprint(story_id):
    session = _session_or_404(story_id)
    if not session.blueprint:
        raise ValueError("蓝图尚未生成")
    if session.chapters:
        raise ValueError("第一章已经生成")
    return ok(service.start_job(story_id, "first_chapter", {}).public_dict())


@story_bp.route("/<story_id>/choose", methods=["POST"])
def choose_topic(story_id):
    data = request.get_json() or {}
    return ok(service.choose(story_id, data.get("topic_id"), data.get("custom", "")).public_dict())


@story_bp.route("/<story_id>/regenerate-chapter", methods=["POST"])
def regenerate_chapter(story_id):
    session = _session_or_404(story_id)
    if not session.chapters:
        raise ValueError("还没有章节")
    return ok(service.start_job(story_id, "regenerate", {}).public_dict())


@story_bp.route("/<story_id>/rewind", methods=["POST"])
def rewind(story_id):
    keep = int((request.get_json() or {}).get("keep_chapters", 0))
    return ok(service.rewind(story_id, keep).public_dict())


@story_bp.route("/<story_id>/retry", methods=["POST"])
def retry(story_id):
    return ok(service.retry(story_id).public_dict())


@story_bp.route("/<story_id>/download", methods=["GET"])
def download(story_id):
    # 从内存渲染，避免下载过程中占用文件导致后台保存失败（Windows）
    session = _session_or_404(story_id)
    name = (session.blueprint.title if session.blueprint else story_id) + ".md"
    data = io.BytesIO(store.render_markdown(session).encode("utf-8"))
    return send_file(data, as_attachment=True, download_name=name, mimetype="text/markdown")
