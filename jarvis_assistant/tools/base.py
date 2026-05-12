from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


ToolHandler = Callable[..., "ToolResult"]


@dataclass(slots=True)
class ToolResult:
    tool: str
    ok: bool
    content: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, str]
    handler: ToolHandler

    def prompt_line(self) -> str:
        params = ", ".join(f"{name}: {kind}" for name, kind in self.parameters.items())
        return f"- {self.name}({params}) - {self.description}"
