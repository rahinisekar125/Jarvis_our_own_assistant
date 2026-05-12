from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..config import AssistantSettings
from ..executor.executor import ToolExecutor
from ..tools.base import ToolResult
from ..tools.registry import ToolRegistry
from .llm import LLMClient, Message
from .fast_intents import match_fast_intent
from .language import prefers_hinglish
from .memory import MemoryStore
from .prompts import build_system_prompt
from .schemas import AgentDecision, parse_agent_decision

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class AgentResult:
    ok: bool
    response: str
    tool_results: list[ToolResult] = field(default_factory=list)


class JarvisAgent:
    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        executor: ToolExecutor,
        memory: MemoryStore,
        assistant_settings: AssistantSettings,
    ) -> None:
        self.llm = llm
        self.registry = registry
        self.executor = executor
        self.memory = memory
        self.assistant_settings = assistant_settings

    def process(self, user_text: str) -> AgentResult:
        user_text = user_text.strip()
        if not user_text:
            return AgentResult(ok=False, response="I did not hear a command.")

        self.memory.log_event("user", user_text)
        fast_decision = match_fast_intent(user_text)
        if fast_decision is not None:
            return self._complete_decision(user_text, fast_decision, notices=[])

        messages = self._build_messages(user_text)

        try:
            raw = self.llm.complete(messages)
            notices = _consume_llm_notices(self.llm)
            decision = parse_agent_decision(raw)
        except Exception as exc:  # noqa: BLE001 - surface a useful assistant response.
            LOGGER.exception("LLM response failed")
            response = f"I could not understand the model response: {exc}"
            self.memory.log_event("assistant", response)
            return AgentResult(ok=False, response=response)

        self._apply_memory_updates(decision)
        return self._complete_decision(user_text, decision, notices=notices)

    def _complete_decision(
        self,
        user_text: str,
        decision: AgentDecision,
        notices: list[str],
    ) -> AgentResult:
        if decision.tool_calls:
            results = self.executor.execute_many(user_text, decision.tool_calls)
            response = _join_notices(notices, _tool_response(decision, results, user_text))
            self.memory.log_event("assistant", response)
            return AgentResult(
                ok=all(result.ok for result in results),
                response=response,
                tool_results=results,
            )

        response = _join_notices(notices, decision.message or "Done.")
        self.memory.log_event("assistant", response)
        return AgentResult(ok=True, response=response)

    def _build_messages(self, user_text: str) -> list[Message]:
        system_prompt = build_system_prompt(
            assistant_name=self.assistant_settings.name,
            registry=self.registry,
            memory_summary=self.memory.memory_summary(),
            user_text=user_text,
        )
        messages: list[Message] = [{"role": "system", "content": system_prompt}]

        for event in self.memory.recent_events(limit=8):
            role = "assistant" if event["role"] == "assistant" else "user"
            messages.append({"role": role, "content": event["content"]})

        messages.append({"role": "user", "content": user_text})
        return messages

    def _apply_memory_updates(self, decision: AgentDecision) -> None:
        for item in decision.memory_updates:
            self.memory.remember(item.kind, item.key, item.value, item.importance)


def _tool_results_text(results: list[ToolResult], user_text: str) -> str:
    lines: list[str] = []
    hinglish = prefers_hinglish(user_text)
    for result in results:
        content = result.content.strip() or "Done."
        if result.ok:
            lines.append(_natural_tool_success(result, user_text, hinglish) or content)
        else:
            if hinglish:
                lines.append(f"{result.tool} fail ho gaya: {content}")
            else:
                lines.append(f"{result.tool} failed: {content}")
    return "\n".join(lines)


def _tool_response(decision: AgentDecision, results: list[ToolResult], user_text: str) -> str:
    if not results:
        return decision.message or "Done."
    return _tool_results_text(results, user_text)


def _natural_tool_success(result: ToolResult, user_text: str, hinglish: bool) -> str | None:
    data = result.data or {}
    if result.tool == "open_application":
        app_name = str(data.get("app_name") or _friendly_target(data.get("target")) or "application")
        return f"{app_name} khol diya." if hinglish else f"Opened {app_name}."

    if result.tool == "open_application_and_type":
        app_name = str(data.get("app_name") or "application")
        if hinglish:
            return f"{app_name} khol kar text type kar diya."
        return f"Opened {app_name} and typed the text."

    if result.tool == "control_browser":
        if _looks_like_play_command(user_text):
            return "YouTube par chala raha hoon." if hinglish else "Playing it on YouTube."
        return "Browser khol diya." if hinglish else "Opened browser."

    if result.tool == "web_search":
        prefix = "Yeh results mile:" if hinglish else "Here are the results:"
        return f"{prefix}\n{result.content.strip()}"

    if result.tool == "get_system_info" and data:
        return _format_system_info(data, hinglish)

    return None


def _format_system_info(data: dict, hinglish: bool) -> str:
    cpu = data.get("cpu_percent")
    memory = data.get("memory_percent")
    disk = data.get("disk_percent")
    battery = data.get("battery_percent")
    plugged = data.get("plugged_in")
    if hinglish:
        parts = [f"CPU {cpu}%", f"memory {memory}%", f"disk {disk}%"]
        if battery is not None:
            plug_text = "charging hai" if plugged else "charging nahi hai"
            parts.append(f"battery {battery}% hai, {plug_text}")
        return ", ".join(parts) + "."

    lines = [f"CPU: {cpu}%", f"Memory: {memory}%", f"Disk: {disk}%"]
    if battery is not None:
        plug_text = "plugged in" if plugged else "not plugged in"
        lines.append(f"Battery: {battery}% ({plug_text})")
    return "\n".join(lines)


def _friendly_target(target: object) -> str:
    text = str(target or "").strip()
    if not text:
        return ""
    name = text.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    for suffix in (".exe", ".cmd", ".bat", ".ps1"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return name


def _looks_like_play_command(user_text: str) -> bool:
    text = user_text.lower()
    return text.startswith("play ") or text.endswith(" chalao") or text.endswith(" bajao")


def _consume_llm_notices(llm: object) -> list[str]:
    consume = getattr(llm, "consume_notices", None)
    if callable(consume):
        return [str(item) for item in consume()]
    return []


def _join_notices(notices: list[str], response: str) -> str:
    clean_notices = [notice.strip() for notice in notices if notice.strip()]
    if not clean_notices:
        return response
    return "\n".join([*clean_notices, response])
