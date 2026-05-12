from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(slots=True)
class RetryConfig:
    max_attempts: int = 5
    base_delay_seconds: float = 2.0
    max_delay_seconds: float = 30.0


class RetryExhaustedError(RuntimeError):
    def __init__(self, provider: str, model: str, last_error: Exception) -> None:
        self.provider = provider
        self.model = model
        self.last_error = last_error
        super().__init__(f"{provider}:{model} failed after retries: {_safe_error(last_error)}")


class RetryHandler:
    def __init__(self, config: RetryConfig) -> None:
        self.config = config

    def run(self, provider: str, model: str, operation: Callable[[], T]) -> T:
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                LOGGER.info(
                    "LLM request attempt=%s/%s provider=%s model=%s",
                    attempt,
                    self.config.max_attempts,
                    provider,
                    model,
                )
                result = operation()
                LOGGER.info("LLM request succeeded provider=%s model=%s", provider, model)
                return result
            except Exception as exc:  # noqa: BLE001 - retry layer intentionally normalizes provider errors.
                last_error = exc
                status_code = get_status_code(exc)
                retryable = is_retryable(exc)
                LOGGER.warning(
                    "LLM request failed attempt=%s/%s provider=%s model=%s status=%s error=%s retryable=%s",
                    attempt,
                    self.config.max_attempts,
                    provider,
                    model,
                    status_code or "n/a",
                    _safe_error(exc),
                    retryable,
                )

                if attempt >= self.config.max_attempts or not retryable:
                    break

                delay = retry_after_seconds(exc)
                if delay is None:
                    delay = min(
                        self.config.base_delay_seconds * (2 ** (attempt - 1)),
                        self.config.max_delay_seconds,
                    )
                LOGGER.info(
                    "LLM retry scheduled provider=%s model=%s delay_seconds=%.1f",
                    provider,
                    model,
                    delay,
                )
                time.sleep(delay)

        if last_error is None:
            last_error = RuntimeError("unknown retry failure")
        raise RetryExhaustedError(provider=provider, model=model, last_error=last_error) from last_error


def get_status_code(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    return None


def retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    value = headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def is_retryable(exc: Exception) -> bool:
    status_code = get_status_code(exc)
    if status_code in {408, 409, 429, 500, 502, 503, 504}:
        return True
    module = exc.__class__.__module__
    name = exc.__class__.__name__.lower()
    if module.startswith("requests") and any(token in name for token in ("timeout", "connection")):
        return True
    return False


def _safe_error(exc: Exception) -> str:
    status_code = get_status_code(exc)
    if status_code is not None:
        return f"HTTP {status_code}"
    if exc.__class__.__module__.startswith("requests"):
        return exc.__class__.__name__
    return str(exc)
