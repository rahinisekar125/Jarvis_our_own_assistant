from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import Any

from ..agent.memory import MemoryStore
from ..agent.schemas import ToolCall
from ..audio.tts import Speaker
from ..tools.base import ToolResult
from ..tools.registry import ToolRegistry
from .safety import SafetyPolicy

LOGGER = logging.getLogger(__name__)


class ConfirmationProvider:
    def confirm(self, prompt: str) -> bool:
        raise NotImplementedError


@dataclass(slots=True)
class ConsoleConfirmationProvider(ConfirmationProvider):
    speaker: Speaker | None = None

    def confirm(self, prompt: str) -> bool:
        if self.speaker is not None:
            self.speaker.speak(prompt)
        answer = input(f"{prompt} [y/N] ").strip().lower()
        return answer in {"y", "yes"}


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        safety: SafetyPolicy,
        confirmer: ConfirmationProvider,
        memory: MemoryStore,
    ) -> None:
        self.registry = registry
        self.safety = safety
        self.confirmer = confirmer
        self.memory = memory

    def execute_many(self, user_text: str, calls: list[ToolCall]) -> list[ToolResult]:
        return [self.execute(user_text, call) for call in calls]

    def execute(self, user_text: str, call: ToolCall) -> ToolResult:
        try:
            spec = self.registry.get(call.tool)
        except KeyError as exc:
            return ToolResult(tool=call.tool, ok=False, content=str(exc))

        decision = self.safety.evaluate(call.tool, call.arguments)
        if not decision.allowed:
            result = ToolResult(tool=call.tool, ok=False, content=f"Blocked: {decision.reason}")
            self._log(user_text, call, result)
            return result

        if decision.requires_confirmation:
            prompt = (
                f"Confirm {call.tool} with risk={decision.risk.value}: "
                f"{decision.reason} Arguments: {call.arguments}"
            )
            if not self.confirmer.confirm(prompt):
                result = ToolResult(tool=call.tool, ok=False, content="User declined confirmation.")
                self._log(user_text, call, result)
                return result

        try:
            kwargs = _filter_kwargs(spec.handler, call.arguments)
            result = spec.handler(**kwargs)
        except Exception as exc:  # noqa: BLE001 - tool errors become observations.
            LOGGER.exception("Tool failed: %s", call.tool)
            result = ToolResult(tool=call.tool, ok=False, content=f"Tool failed: {exc}")

        self._log(user_text, call, result)
        return result

    def _log(self, user_text: str, call: ToolCall, result: ToolResult) -> None:
        self.memory.log_command(
            user_text=user_text,
            tool_name=call.tool,
            arguments=call.arguments,
            status="ok" if result.ok else "error",
            summary=result.content,
        )


def _filter_kwargs(handler: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    signature = inspect.signature(handler)
    allowed = {
        name
        for name, param in signature.parameters.items()
        if param.kind in {param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY}
    }
    return {key: value for key, value in arguments.items() if key in allowed}
