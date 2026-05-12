from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..config import SecuritySettings


class Risk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


@dataclass(slots=True)
class SafetyDecision:
    allowed: bool
    requires_confirmation: bool
    risk: Risk
    reason: str


class SafetyPolicy:
    BLOCKED_PATTERNS = [
        r"\bformat\b",
        r"\bcipher\s+/w\b",
        r"\bbcdedit\b",
        r"\breg\s+delete\b",
        r"\btakeown\b",
        r"\bicacls\b.*\s/grant\b",
        r"\bnet\s+user\b",
        r"\bshutdown\b",
        r"\brestart-computer\b",
        r"\bstop-computer\b",
        r"\bset-executionpolicy\b",
        r"(?:irm|iwr|curl|wget).*(?:\||;).*(?:iex|powershell|cmd)",
        r"remove-item\s+.*(?:c:\\|/)\s*-recurse",
        r"\brm\s+-rf\s+(?:/|c:\\|~)",
        r"\bdel\s+/[sfq]\s+(?:c:\\|\\|/)",
    ]

    HIGH_RISK_PATTERNS = [
        r"\bremove-item\b",
        r"\brm\s+-rf\b",
        r"\bdel\b",
        r"\brmdir\b",
        r"\bgit\s+reset\s+--hard\b",
        r"\bgit\s+clean\b",
        r"\bdocker\s+system\s+prune\b",
        r"\bdocker\s+volume\s+rm\b",
        r"\bkubectl\s+delete\b",
        r"\bdrop\s+database\b",
        r"\bnpm\s+publish\b",
        r"\bdeploy\b",
    ]

    def __init__(self, settings: SecuritySettings) -> None:
        self.settings = settings

    def evaluate(self, tool_name: str, arguments: dict[str, Any]) -> SafetyDecision:
        if tool_name == "run_shell_command":
            return self._evaluate_shell(str(arguments.get("command", "")))
        if tool_name == "write_file":
            return SafetyDecision(True, True, Risk.MEDIUM, "Writing files requires confirmation.")
        if tool_name == "manage_projects":
            return self._evaluate_project_action(str(arguments.get("action", "")))
        if tool_name in {
            "read_file",
            "get_system_info",
            "web_search",
            "control_browser",
            "open_application",
            "open_application_and_type",
        }:
            return SafetyDecision(True, False, Risk.LOW, "Low-risk tool.")
        return SafetyDecision(False, False, Risk.BLOCKED, f"Unknown tool: {tool_name}")

    def _evaluate_shell(self, command: str) -> SafetyDecision:
        normalized = command.strip().lower()
        if not normalized:
            return SafetyDecision(False, False, Risk.BLOCKED, "Empty shell command.")

        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, normalized, re.IGNORECASE):
                return SafetyDecision(False, False, Risk.BLOCKED, f"Blocked dangerous command pattern: {pattern}")

        for pattern in self.HIGH_RISK_PATTERNS:
            if re.search(pattern, normalized, re.IGNORECASE):
                return SafetyDecision(True, True, Risk.HIGH, "High-risk shell command requires confirmation.")

        if self.settings.require_confirmation_for_shell:
            return SafetyDecision(True, True, Risk.MEDIUM, "Shell commands require confirmation by configuration.")

        return SafetyDecision(True, False, Risk.MEDIUM, "Shell command allowed after validation.")

    def _evaluate_project_action(self, action: str) -> SafetyDecision:
        normalized = action.strip().lower().replace(" ", "_").replace("-", "_")
        if normalized in {"deploy", "docker_compose_down", "git_pull", "docker_run"}:
            return SafetyDecision(True, True, Risk.HIGH, f"{normalized} requires confirmation.")
        if normalized in {
            "git_status",
            "status",
            "git_log",
            "github_pr_status",
            "docker_ps",
            "docker_build",
            "docker_compose_up",
            "open_today_tasks",
        }:
            return SafetyDecision(True, False, Risk.LOW, "Allowlisted project workflow.")
        return SafetyDecision(False, False, Risk.BLOCKED, f"Unsupported project action: {action}")
