from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

LOGGER = logging.getLogger(__name__)

Message = dict[str, str]


class LLMClient(ABC):
    @abstractmethod
    def complete(self, messages: list[Message]) -> str:
        raise NotImplementedError


class OllamaClient(LLMClient):
    def __init__(self, base_url: str, model: str, temperature: float, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds

    def complete(self, messages: list[Message]) -> str:
        import requests

        response = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "format": "json",
                "keep_alive": "30m",
                "options": {
                    "temperature": self.temperature,
                    "num_ctx": 1024,
                    "num_predict": 64,
                    "top_k": 20,
                    "top_p": 0.8,
                },
            },
            timeout=self.timeout_seconds,
        )
        LOGGER.info(
            "Ollama response status=%s model=%s",
            response.status_code,
            self.model,
        )
        response.raise_for_status()
        data = response.json()
        return str(data.get("message", {}).get("content", "")).strip()


class GeminiClient(LLMClient):
    def __init__(self, api_key: str, model: str, temperature: float, timeout_seconds: int) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required for Gemini provider")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds

    def complete(self, messages: list[Message]) -> str:
        import requests

        system_text = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = []
        for message in messages:
            if message["role"] == "system":
                continue
            role = "model" if message["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": message["content"]}]})

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.temperature,
                "responseMimeType": "application/json",
            },
        }
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}

        response = requests.post(
            url,
            json=payload,
            headers={"x-goog-api-key": self.api_key},
            timeout=self.timeout_seconds,
        )
        LOGGER.info(
            "Gemini response status=%s model=%s",
            response.status_code,
            self.model,
        )
        response.raise_for_status()
        data = response.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected Gemini response: {data}") from exc


class RuleBasedFallbackClient(LLMClient):
    """Small fallback so the project remains runnable before configuring an LLM."""

    def complete(self, messages: list[Message]) -> str:
        last_text = _last_user_text(messages)
        user_text = last_text.lower()

        if "system" in user_text and ("info" in user_text or "status" in user_text):
            return _json_tool("get_system_info", {})
        if user_text.startswith("open "):
            return _json_tool("open_application", {"app_name": user_text.removeprefix("open ").strip()})
        if "git status" in user_text:
            return _json_tool("manage_projects", {"action": "git_status"})
        if "today" in user_text and "tasks" in user_text:
            return _json_tool("manage_projects", {"action": "open_today_tasks"})
        if user_text.startswith("search ") or "web search" in user_text:
            query = user_text.replace("web search", "").replace("search", "", 1).strip()
            return _json_tool("web_search", {"query": query})

        return json.dumps(
            {
                "status": "final",
                "message": (
                    "I can handle basic local commands right now. For richer autonomous "
                    "planning, I need Gemini or Ollama to be reachable."
                ),
                "plan": [],
                "tool_calls": [],
                "memory_updates": [],
            }
        )


def _json_tool(tool: str, arguments: dict[str, Any]) -> str:
    return json.dumps(
        {
            "status": "tool_call",
            "message": "I'll take a look.",
            "plan": [],
            "tool_calls": [{"tool": tool, "arguments": arguments}],
            "memory_updates": [],
        }
    )


def _last_user_text(messages: list[Message]) -> str:
    for message in reversed(messages):
        if message["role"] == "user":
            return message["content"]
    return ""
