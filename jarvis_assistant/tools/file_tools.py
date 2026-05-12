from __future__ import annotations

from pathlib import Path

from ..config import Settings
from .base import ToolResult, ToolSpec


def build_file_tools(settings: Settings) -> list[ToolSpec]:
    def read_file(path: str) -> ToolResult:
        resolved = _resolve_allowed(path, settings.security.allowed_paths)
        size = resolved.stat().st_size
        if size > settings.security.file_read_limit_bytes:
            return ToolResult(
                tool="read_file",
                ok=False,
                content=(
                    f"File is {size} bytes, which exceeds the configured read limit "
                    f"of {settings.security.file_read_limit_bytes} bytes."
                ),
            )
        content = resolved.read_text(encoding="utf-8", errors="replace")
        return ToolResult(
            tool="read_file",
            ok=True,
            content=content,
            data={"path": str(resolved), "bytes": size},
        )

    def write_file(path: str, content: str) -> ToolResult:
        resolved = _resolve_allowed(path, settings.security.allowed_paths)
        existed = resolved.exists()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return ToolResult(
            tool="write_file",
            ok=True,
            content=f"{'Updated' if existed else 'Created'} {resolved}",
            data={"path": str(resolved), "bytes": len(content.encode("utf-8"))},
        )

    return [
        ToolSpec(
            name="read_file",
            description="Read a UTF-8 text file from an allowed path.",
            parameters={"path": "string"},
            handler=read_file,
        ),
        ToolSpec(
            name="write_file",
            description="Write UTF-8 text to a file under an allowed path.",
            parameters={"path": "string", "content": "string"},
            handler=write_file,
        ),
    ]


def _resolve_allowed(path: str, allowed_roots: list[Path]) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    resolved = candidate.resolve()

    for root in allowed_roots:
        root = root.resolve()
        if resolved == root or root in resolved.parents:
            return resolved

    allowed = ", ".join(str(root) for root in allowed_roots)
    raise PermissionError(f"Path is outside allowed roots: {resolved}. Allowed roots: {allowed}")
