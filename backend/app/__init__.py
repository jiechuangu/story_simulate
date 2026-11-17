"""Story Simulate 后端 - Flask 应用工厂"""

import os

from flask import Flask
from flask_cors import CORS

from .config import Config
from .utils.logger import get_logger, setup_logger


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    if hasattr(app, "json") and hasattr(app.json, "ensure_ascii"):
        app.json.ensure_ascii = False

    setup_logger("story")
    logger = get_logger("story")
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    from .api import story_bp

    app.register_blueprint(story_bp, url_prefix="/api/story")

    @app.route("/health")
    def health():
        return {"status": "ok"}

    # debug 模式下只在 reloader 子进程里做恢复
    if not app.config.get("DEBUG") or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from .story.store import recover_interrupted

        n = recover_interrupted()
        if n:
            logger.info("已将 %d 个中断的任务标记为失败，可在页面上重试", n)
        logger.info("Story Simulate 后端已启动")
    return app
