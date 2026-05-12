from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from jarvis_assistant.agent.llm import LLMClient, Message, RuleBasedFallbackClient
from jarvis_assistant.agent.llm_manager import LLMManager, LLMRoute
from jarvis_assistant.agent.retry_handler import RetryConfig, RetryHandler


class FakeResponse:
    def __init__(self, status_code: int, retry_after: str | None = None) -> None:
        self.status_code = status_code
        self.headers = {}
        if retry_after is not None:
            self.headers["Retry-After"] = retry_after


class FakeHTTPError(Exception):
    def __init__(self, status_code: int, retry_after: str | None = None) -> None:
        self.response = FakeResponse(status_code, retry_after)
        super().__init__(f"HTTP {status_code}")


class FailingClient(LLMClient):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.calls = 0

    def complete(self, messages: list[Message]) -> str:
        self.calls += 1
        raise FakeHTTPError(self.status_code)


class SuccessClient(LLMClient):
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages: list[Message]) -> str:
        self.calls += 1
        return json.dumps({"status": "final", "message": "backup ok", "tool_calls": []})


class RetryManagerTests(unittest.TestCase):
    def test_switches_to_ollama_after_gemini_retries(self) -> None:
        gemini = FailingClient(503)
        ollama = SuccessClient()
        retry = RetryHandler(RetryConfig(max_attempts=3, base_delay_seconds=0, max_delay_seconds=0))
        manager = LLMManager(
            routes=[
                LLMRoute(
                    provider="gemini",
                    model="gemini-1.5-flash",
                    client=gemini,
                    retry_handler=retry,
                ),
                LLMRoute(
                    provider="ollama",
                    model="llama3.1:8b",
                    client=ollama,
                    retry_handler=retry,
                ),
            ],
            fallback=RuleBasedFallbackClient(),
            retry_handler=retry,
            cooldown_seconds=0,
        )

        with patch("jarvis_assistant.agent.retry_handler.time.sleep"):
            result = manager.complete([{"role": "user", "content": "hello"}])

        self.assertIn("backup ok", result)
        self.assertEqual(gemini.calls, 3)
        self.assertEqual(ollama.calls, 1)
        self.assertEqual(manager.last_provider, "ollama")
        self.assertIn("switching to backup", " ".join(manager.consume_notices()))

    def test_uses_basic_local_mode_only_after_all_routes_fail(self) -> None:
        gemini = FailingClient(429)
        ollama = FailingClient(503)
        retry = RetryHandler(RetryConfig(max_attempts=2, base_delay_seconds=0, max_delay_seconds=0))
        manager = LLMManager(
            routes=[
                LLMRoute(
                    provider="gemini",
                    model="gemini-1.5-flash",
                    client=gemini,
                    retry_handler=retry,
                ),
                LLMRoute(
                    provider="ollama",
                    model="llama3.1:8b",
                    client=ollama,
                    retry_handler=retry,
                ),
            ],
            fallback=RuleBasedFallbackClient(),
            retry_handler=retry,
            cooldown_seconds=0,
        )

        with patch("jarvis_assistant.agent.retry_handler.time.sleep"):
            result = manager.complete([{"role": "user", "content": "show system info"}])

        self.assertIn("get_system_info", result)
        self.assertEqual(gemini.calls, 2)
        self.assertEqual(ollama.calls, 2)
        self.assertEqual(manager.last_provider, "fallback")


if __name__ == "__main__":
    unittest.main()
