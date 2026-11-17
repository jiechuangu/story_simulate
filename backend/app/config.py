"""
配置管理：统一从项目根目录的 .env 加载。
"""

import os

from dotenv import load_dotenv

_root_env = os.path.join(os.path.dirname(__file__), "../../.env")
if os.path.exists(_root_env):
    load_dotenv(_root_env, override=True)
else:
    load_dotenv(override=True)


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "story-simulate")
    DEBUG = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    JSON_AS_ASCII = False

    # LLM（OpenAI 兼容接口）
    LLM_API_KEY = os.environ.get("LLM_API_KEY")
    LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "gpt-4o-mini")
    # 可选：写正文/润色使用更强的模型；不填则与 LLM_MODEL_NAME 相同
    LLM_WRITER_MODEL_NAME = os.environ.get("LLM_WRITER_MODEL_NAME") or None
    LLM_TIMEOUT = _int("LLM_TIMEOUT", 300)
    # 被截断时自动加大 max_tokens 的上限（推理模型的思考过程也计入额度）
    LLM_MAX_TOKENS_CAP = _int("LLM_MAX_TOKENS_CAP", 32000)

    # 存储
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    UPLOAD_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), "../uploads"))
    STORIES_DIR = os.path.join(UPLOAD_FOLDER, "stories")
    ALLOWED_EXTENSIONS = {"pdf", "md", "txt", "markdown"}

    # 故事模拟参数
    SOURCE_DIRECT_LIMIT = _int("STORY_SOURCE_DIRECT_LIMIT", 12000)   # 素材短于此长度直接使用
    SOURCE_CHUNK_SIZE = _int("STORY_SOURCE_CHUNK_SIZE", 8000)
    SOURCE_MAX_CHUNKS = _int("STORY_SOURCE_MAX_CHUNKS", 24)
    SCENE_ROUNDS = _int("STORY_SCENE_ROUNDS", 2)                     # 每个场景角色轮流行动的轮数
    SCENE_MAX_CHARACTERS = _int("STORY_SCENE_MAX_CHARACTERS", 3)
    MAX_SCENES = _int("STORY_MAX_SCENES", 2)
    MAX_NEW_CHARACTERS = _int("STORY_MAX_NEW_CHARACTERS", 1)          # 每章导演最多新登记的人物数
    PREV_TAIL_CHARS = _int("STORY_PREV_TAIL_CHARS", 1500)            # 写作时带入上一章原文结尾的长度

    @classmethod
    def validate(cls):
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY 未配置")
        return errors
