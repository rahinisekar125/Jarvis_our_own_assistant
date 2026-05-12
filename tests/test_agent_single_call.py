from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jarvis_assistant.agent.agent import JarvisAgent
from jarvis_assistant.agent.llm import LLMClient, Message
from jarvis_assistant.agent.memory import MemoryStore
from jarvis_assistant.config import AssistantSettings, SecuritySettings
from jarvis_assistant.executor.executor import ConsoleConfirmationProvider, ToolExecutor
from jarvis_assistant.executor.safety import SafetyPolicy
from jarvis_assistant.tools.base import ToolResult, ToolSpec
from jarvis_assistant.tools.registry import ToolRegistry


class FakePlanningLLM(LLMClient):
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages: list[Message]) -> str:
        self.calls += 1
        return json.dumps(
            {
                "status": "tool_call",
                "message": "Checking.",
                "tool_calls": [{"tool": "get_system_info", "arguments": {}}],
            }
        )


class AgentSingleCallTests(unittest.TestCase):
    def test_agent_uses_one_llm_planning_call_for_tool_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = ToolRegistry()
            registry.register(
                ToolSpec(
                    name="get_system_info",
                    description="Fake system info.",
                    parameters={},
                    handler=lambda: ToolResult(
                        tool="get_system_info",
                        ok=True,
                        content="CPU: 10%",
                    ),
                )
            )
            memory = MemoryStore(Path(temp_dir) / "memory.sqlite3")
            executor = ToolExecutor(
                registry=registry,
                safety=SafetyPolicy(
                    SecuritySettings(
                        allowed_paths=[Path(temp_dir)],
                        command_timeout_seconds=5,
                        file_read_limit_bytes=1000,
                        require_confirmation_for_shell=False,
                    )
                ),
                confirmer=ConsoleConfirmationProvider(),
                memory=memory,
            )
            llm = FakePlanningLLM()
            agent = JarvisAgent(
                llm=llm,
                registry=registry,
                executor=executor,
                memory=memory,
                assistant_settings=AssistantSettings(name="Jarvis", max_tool_rounds=5),
            )

            result = agent.process("show system info")

        self.assertTrue(result.ok)
        self.assertEqual(llm.calls, 1)
        self.assertEqual(result.response, "CPU: 10%")

    def test_fast_intent_skips_llm_for_simple_math(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = ToolRegistry()
            memory = MemoryStore(Path(temp_dir) / "memory.sqlite3")
            executor = ToolExecutor(
                registry=registry,
                safety=SafetyPolicy(
                    SecuritySettings(
                        allowed_paths=[Path(temp_dir)],
                        command_timeout_seconds=5,
                        file_read_limit_bytes=1000,
                        require_confirmation_for_shell=False,
                    )
                ),
                confirmer=ConsoleConfirmationProvider(),
                memory=memory,
            )
            llm = FakePlanningLLM()
            agent = JarvisAgent(
                llm=llm,
                registry=registry,
                executor=executor,
                memory=memory,
                assistant_settings=AssistantSettings(name="Jarvis", max_tool_rounds=5),
            )

            result = agent.process("what is 2 plus 2")

        self.assertTrue(result.ok)
        self.assertEqual(llm.calls, 0)
        self.assertEqual(result.response, "The answer is 4.")

    def test_hinglish_tool_result_is_spoken_in_hinglish(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = ToolRegistry()
            registry.register(
                ToolSpec(
                    name="get_system_info",
                    description="Fake system info.",
                    parameters={},
                    handler=lambda: ToolResult(
                        tool="get_system_info",
                        ok=True,
                        content="CPU: 10%",
                        data={
                            "cpu_percent": 10,
                            "memory_percent": 20,
                            "disk_percent": 30,
                            "battery_percent": 80,
                            "plugged_in": True,
                        },
                    ),
                )
            )
            memory = MemoryStore(Path(temp_dir) / "memory.sqlite3")
            executor = ToolExecutor(
                registry=registry,
                safety=SafetyPolicy(
                    SecuritySettings(
                        allowed_paths=[Path(temp_dir)],
                        command_timeout_seconds=5,
                        file_read_limit_bytes=1000,
                        require_confirmation_for_shell=False,
                    )
                ),
                confirmer=ConsoleConfirmationProvider(),
                memory=memory,
            )
            llm = FakePlanningLLM()
            agent = JarvisAgent(
                llm=llm,
                registry=registry,
                executor=executor,
                memory=memory,
                assistant_settings=AssistantSettings(name="Jarvis", max_tool_rounds=5),
            )

            result = agent.process("battery batao")

        self.assertTrue(result.ok)
        self.assertEqual(llm.calls, 0)
        self.assertIn("battery 80% hai", result.response)
        self.assertIn("charging hai", result.response)


if __name__ == "__main__":
    unittest.main()
