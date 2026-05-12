from __future__ import annotations

from ..config import Settings
from .file_tools import build_file_tools
from .project_tools import build_project_tools
from .registry import ToolRegistry
from .system_tools import build_system_tools
from .web_tools import build_web_tools


def build_default_registry(settings: Settings) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in (
        *build_system_tools(settings),
        *build_file_tools(settings),
        *build_web_tools(settings),
        *build_project_tools(settings),
    ):
        registry.register(tool)
    return registry
