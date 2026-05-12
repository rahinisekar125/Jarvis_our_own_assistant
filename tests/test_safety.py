from __future__ import annotations

from pathlib import Path
import unittest

from jarvis_assistant.config import SecuritySettings
from jarvis_assistant.executor.safety import Risk, SafetyPolicy


class SafetyPolicyTests(unittest.TestCase):
    def policy(self) -> SafetyPolicy:
        return SafetyPolicy(
            SecuritySettings(
                allowed_paths=[Path.cwd()],
                command_timeout_seconds=10,
                file_read_limit_bytes=1000,
                require_confirmation_for_shell=False,
            )
        )

    def test_blocks_format_command(self) -> None:
        decision = self.policy().evaluate("run_shell_command", {"command": "format C:"})
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.risk, Risk.BLOCKED)

    def test_requires_confirmation_for_delete(self) -> None:
        decision = self.policy().evaluate("run_shell_command", {"command": "Remove-Item old.txt"})
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.requires_confirmation)
        self.assertEqual(decision.risk, Risk.HIGH)

    def test_allows_read_only_project_status(self) -> None:
        decision = self.policy().evaluate("manage_projects", {"action": "git_status"})
        self.assertTrue(decision.allowed)
        self.assertFalse(decision.requires_confirmation)


if __name__ == "__main__":
    unittest.main()
