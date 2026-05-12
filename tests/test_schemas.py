from __future__ import annotations

import unittest

from jarvis_assistant.agent.schemas import parse_agent_decision


class AgentSchemaTests(unittest.TestCase):
    def test_parse_json_fenced_decision(self) -> None:
        decision = parse_agent_decision(
            """```json
            {"status":"tool_call","message":"ok","tool_calls":[{"tool":"get_system_info","arguments":{}}]}
            ```"""
        )
        self.assertEqual(decision.status, "tool_call")
        self.assertEqual(decision.tool_calls[0].tool, "get_system_info")

    def test_parse_memory_updates(self) -> None:
        decision = parse_agent_decision(
            """
            Here is the object:
            {"status":"final","message":"Saved.","memory_updates":[{"kind":"preference","key":"voice","value":"brief","importance":2}]}
            """
        )
        self.assertEqual(decision.message, "Saved.")
        self.assertEqual(decision.memory_updates[0].key, "voice")


if __name__ == "__main__":
    unittest.main()
