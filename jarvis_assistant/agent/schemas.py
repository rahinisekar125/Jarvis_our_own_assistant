from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolCall:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MemoryUpdate:
    kind: str
    key: str
    value: str
    importance: int = 1


@dataclass(slots=True)
class AgentDecision:
    status: str
    message: str = ""
    plan: list[str] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    memory_updates: list[MemoryUpdate] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "status": self.status,
                "message": self.message,
                "plan": self.plan,
                "tool_calls": [
                    {"tool": call.tool, "arguments": call.arguments} for call in self.tool_calls
                ],
                "memory_updates": [
                    {
                        "kind": item.kind,
                        "key": item.key,
                        "value": item.value,
                        "importance": item.importance,
                    }
                    for item in self.memory_updates
                ],
            },
            ensure_ascii=False,
        )


def parse_agent_decision(raw: str) -> AgentDecision:
    payload = _load_json_object(raw)

    calls: list[ToolCall] = []
    for item in _ensure_list(payload.get("tool_calls", [])):
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool", "")).strip()
        if not tool:
            continue
        args = item.get("arguments", {})
        calls.append(ToolCall(tool=tool, arguments=args if isinstance(args, dict) else {}))

    memories: list[MemoryUpdate] = []
    for item in _ensure_list(payload.get("memory_updates", [])):
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        value = str(item.get("value", "")).strip()
        if not key or not value:
            continue
        memories.append(
            MemoryUpdate(
                kind=str(item.get("kind", "note")).strip() or "note",
                key=key,
                value=value,
                importance=int(item.get("importance", 1) or 1),
            )
        )

    plan = [str(item) for item in _ensure_list(payload.get("plan", []))]
    status = str(payload.get("status", "final")).strip().lower()
    if calls:
        status = "tool_call"

    return AgentDecision(
        status=status if status in {"tool_call", "final"} else "final",
        message=str(payload.get("message", "")).strip(),
        plan=plan,
        tool_calls=calls,
        memory_updates=memories,
    )


def _load_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = json.loads(_extract_balanced_object(text))

    if not isinstance(data, dict):
        raise ValueError("LLM response must be a JSON object")
    return data


def _extract_balanced_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        raise ValueError(f"No JSON object found in LLM response: {text[:200]}")

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    raise ValueError("Unbalanced JSON object in LLM response")


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
