from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path
from typing import Any

from ..config import Settings
from .base import ToolResult, ToolSpec


def build_project_tools(settings: Settings) -> list[ToolSpec]:
    def manage_projects(
        action: str,
        path: str | None = None,
        args: dict[str, Any] | None = None,
    ) -> ToolResult:
        args = args or {}
        cwd = _resolve_project_path(path, settings.base_dir, settings.security.allowed_paths)
        normalized = action.strip().lower().replace(" ", "_").replace("-", "_")

        if normalized in {"git_status", "status"}:
            return _run("manage_projects", ["git", "status", "--short"], cwd, settings)
        if normalized == "git_pull":
            return _run("manage_projects", ["git", "pull", "--ff-only"], cwd, settings)
        if normalized == "git_log":
            count = str(int(args.get("count", 8)))
            return _run("manage_projects", ["git", "log", "--oneline", "-n", count], cwd, settings)
        if normalized == "github_pr_status":
            return _run("manage_projects", ["gh", "pr", "status"], cwd, settings)
        if normalized == "docker_ps":
            return _run("manage_projects", ["docker", "ps"], cwd, settings)
        if normalized == "docker_compose_up":
            return _run("manage_projects", ["docker", "compose", "up", "-d"], cwd, settings)
        if normalized == "docker_compose_down":
            return _run("manage_projects", ["docker", "compose", "down"], cwd, settings)
        if normalized == "docker_build":
            tag = str(args.get("tag", cwd.name.lower()))
            return _run("manage_projects", ["docker", "build", "-t", tag, "."], cwd, settings)
        if normalized == "docker_run":
            image = str(args.get("image", "")).strip()
            if not image:
                return ToolResult(
                    tool="manage_projects",
                    ok=False,
                    content="docker_run requires args.image.",
                )
            extra = [str(item) for item in args.get("extra", []) if str(item).strip()]
            return _run("manage_projects", ["docker", "run", *extra, image], cwd, settings)
        if normalized == "deploy":
            return _deploy(cwd, settings)
        if normalized == "open_today_tasks":
            url = os.getenv("CLICKUP_TASKS_URL", "https://app.clickup.com/")
            webbrowser.open(url)
            return ToolResult(
                tool="manage_projects",
                ok=True,
                content=f"Opened today's tasks: {url}",
                data={"url": url},
            )

        return ToolResult(
            tool="manage_projects",
            ok=False,
            content=(
                "Unsupported project action. Supported: git_status, git_pull, git_log, "
                "github_pr_status, docker_ps, docker_compose_up, docker_compose_down, "
                "docker_build, docker_run, deploy, open_today_tasks."
            ),
        )

    return [
        ToolSpec(
            name="manage_projects",
            description=(
                "Run allowlisted developer workflows for git, GitHub CLI, Docker, deployment, "
                "or opening task boards."
            ),
            parameters={
                "action": "string",
                "path": "optional string",
                "args": "optional object",
            },
            handler=manage_projects,
        )
    ]


def _deploy(cwd: Path, settings: Settings) -> ToolResult:
    candidates = [
        cwd / "scripts" / "deploy.ps1",
        cwd / "deploy.ps1",
        cwd / "scripts" / "deploy.bat",
        cwd / "deploy.bat",
    ]
    for script in candidates:
        if script.exists():
            if script.suffix.lower() == ".ps1":
                return _run(
                    "manage_projects",
                    ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                    cwd,
                    settings,
                )
            return _run("manage_projects", [str(script)], cwd, settings)
    return ToolResult(
        tool="manage_projects",
        ok=False,
        content="No deploy script found. Expected scripts/deploy.ps1, deploy.ps1, scripts/deploy.bat, or deploy.bat.",
    )


def _run(tool: str, command: list[str], cwd: Path, settings: Settings) -> ToolResult:
    completed = subprocess.run(
        command,
        cwd=cwd,
        shell=False,
        text=True,
        capture_output=True,
        timeout=settings.security.command_timeout_seconds,
    )
    output = (completed.stdout or "").strip()
    error = (completed.stderr or "").strip()
    content = output if output else error
    if not content:
        content = f"Command exited with code {completed.returncode}."
    return ToolResult(
        tool=tool,
        ok=completed.returncode == 0,
        content=content[:8000],
        data={"returncode": completed.returncode, "command": command, "cwd": str(cwd)},
    )


def _resolve_project_path(path: str | None, default: Path, allowed_roots: list[Path]) -> Path:
    candidate = Path(path).expanduser() if path else default
    if not candidate.is_absolute():
        candidate = default / candidate
    resolved = candidate.resolve()
    for root in allowed_roots:
        root = root.resolve()
        if resolved == root or root in resolved.parents:
            return resolved
    raise PermissionError(f"Project path is outside allowed roots: {resolved}")
