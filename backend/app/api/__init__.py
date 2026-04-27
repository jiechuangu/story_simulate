"""
API路由模块
"""

from flask import Blueprint

graph_bp = Blueprint('graph', __name__)
simulation_bp = Blueprint('simulation', __name__)
story_bp = Blueprint('story', __name__)
world_bp = Blueprint('world', __name__)

from . import graph  # noqa: E402, F401
from . import simulation  # noqa: E402, F401
from . import story  # noqa: E402, F401
from . import world  # noqa: E402, F401
