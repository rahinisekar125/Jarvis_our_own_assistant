from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from ..config import LLMSettings
from .llm import GeminiClient, LLMClient, Message, OllamaClient, RuleBasedFallbackClient
from .retry_handler import RetryConfig, RetryExhaustedError, RetryHandler

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class LLMRoute:
    provider: str
    model: str
    client: LLMClient
    retry_handler: RetryHandler


@dataclass(slots=True)
class LLMManager(LLMClient):
    routes: list[LLMRoute]
    fallback: LLMClient
    retry_handler: RetryHandler
    cooldown_seconds: float = 1.0
    _last_request_at: float = 0.0
    _notices: list[str] = field(default_factory=list)
    _last_provider: str = "none"
    _last_model: str = "none"

    def complete(self, messages: list[Message]) -> str:
        self._notices.clear()
        if not self.routes:
            self._notices.append("I can handle basic local commands, but no full brain is configured yet.")
            self._last_provider = "fallback"
            self._last_model = "local-rules"
            return self.fallback.complete(messages)

        self._respect_cooldown()
        failures: list[str] = []

        for index, route in enumerate(self.routes):
            if index == 1:
                self._notices.append("I'm having trouble reaching my primary brain, switching to backup.")
            elif index > 1:
                self._notices.append("That backup is also unstable, trying another model.")

            try:
                response = route.retry_handler.run(
                    provider=route.provider,
                    model=route.model,
                    operation=lambda route=route: route.client.complete(
                        _compact_for_backup(messages) if route.provider == "ollama" else messages
                    ),
                )
                self._last_provider = route.provider
                self._last_model = route.model
                LOGGER.info("LLM selected provider=%s model=%s", route.provider, route.model)
                return response
            except RetryExhaustedError as exc:
                failures.append(f"{route.provider}:{route.model} {_safe_failure(exc)}")
                LOGGER.warning(
                    "LLM route exhausted provider=%s model=%s reason=%s",
                    route.provider,
                    route.model,
                    _safe_failure(exc),
                )

        if len(self.routes) > 1:
            self._notices.append(
                "Both my primary and backup brains are unavailable, so I'll handle this with local basics."
            )
        else:
            self._notices.append(
                "I'm having trouble reaching my primary brain, so I'll handle this with local basics."
            )
        self._last_provider = "fallback"
        self._last_model = "local-rules"
        LOGGER.error("All LLM routes failed; using fallback. failures=%s", "; ".join(failures))
        return self.fallback.complete(messages)

    def consume_notices(self) -> list[str]:
        notices = list(self._notices)
        self._notices.clear()
        return notices

    @property
    def last_provider(self) -> str:
        return self._last_provider

    @property
    def last_model(self) -> str:
        return self._last_model

    def _respect_cooldown(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.cooldown_seconds:
            delay = self.cooldown_seconds - elapsed
            LOGGER.info("LLM cooldown sleeping %.2fs", delay)
            time.sleep(delay)
        self._last_request_at = time.monotonic()


def create_llm_client(settings: LLMSettings) -> LLMClient:
    provider = settings.provider.lower()
    fallback = RuleBasedFallbackClient()
    if provider == "fallback":
        return LLMManager(
            routes=[],
            fallback=fallback,
            retry_handler=RetryHandler(_retry_config(settings)),
            cooldown_seconds=settings.cooldown_seconds,
        )

    routes: list[LLMRoute] = []
    if provider != "ollama" and settings.gemini_api_key:
        routes.append(
            LLMRoute(
                provider="gemini",
                model=settings.gemini_model,
                client=GeminiClient(
                    api_key=settings.gemini_api_key,
                    model=settings.gemini_model,
                    temperature=settings.temperature,
                    timeout_seconds=settings.timeout_seconds,
                ),
                retry_handler=RetryHandler(_retry_config(settings)),
            )
        )

    if provider == "ollama" or (provider == "gemini" and settings.ollama_backup_enabled):
        routes.append(
            LLMRoute(
                provider="ollama",
                model=settings.ollama_model,
                client=OllamaClient(
                    base_url=settings.ollama_base_url,
                    model=settings.ollama_model,
                    temperature=settings.temperature,
                    timeout_seconds=settings.ollama_timeout_seconds,
                ),
                retry_handler=RetryHandler(_ollama_retry_config(settings)),
            )
        )

    LOGGER.info(
        "LLM manager configured routes=%s",
        ", ".join(f"{route.provider}:{route.model}" for route in routes),
    )
    return LLMManager(
        routes=routes,
        fallback=fallback,
        retry_handler=RetryHandler(_retry_config(settings)),
        cooldown_seconds=settings.cooldown_seconds,
    )


def _retry_config(settings: LLMSettings) -> RetryConfig:
    return RetryConfig(
        max_attempts=settings.max_retries,
        base_delay_seconds=settings.retry_base_delay_seconds,
        max_delay_seconds=settings.retry_max_delay_seconds,
    )


def _ollama_retry_config(settings: LLMSettings) -> RetryConfig:
    return RetryConfig(
        max_attempts=settings.ollama_max_retries,
        base_delay_seconds=1.0,
        max_delay_seconds=3.0,
    )


def _safe_failure(exc: RetryExhaustedError) -> str:
    last_error = exc.last_error
    response = getattr(last_error, "response", None)
    status = getattr(response, "status_code", None)
    if status is not None:
        return f"HTTP {status}"
    if last_error.__class__.__module__.startswith("requests"):
        return last_error.__class__.__name__
    return str(last_error)


def _compact_for_backup(messages: list[Message]) -> list[Message]:
    system = next((message["content"] for message in messages if message["role"] == "system"), "")
    user = ""
    for message in reversed(messages):
        if message["role"] == "user":
            user = message["content"]
            break

    available_tools = ""
    marker = "Available tools:"
    if marker in system:
        available_tools = marker + system.split(marker, 1)[1].split("Respond with exactly", 1)[0]

    compact_system = f"""
You are Jarvis, a local Windows AI assistant backup brain.
Return exactly one JSON object. No markdown.
Schema:
{{
  "status": "tool_call" | "final",
  "message": "short response",
  "plan": ["optional steps"],
  "tool_calls": [{{"tool": "tool_name", "arguments": {{}}}}],
  "memory_updates": []
}}
If a tool is useful, call it. Otherwise answer directly.
Only call tools listed under Available tools. Do not invent tool names.
{available_tools}
""".strip()

    return [
        {"role": "system", "content": compact_system},
        {"role": "user", "content": user},
    ]
