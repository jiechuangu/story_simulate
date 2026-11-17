"""API 路由"""

from flask import Blueprint

story_bp = Blueprint("story", __name__)

from . import story  # noqa: E402, F401
