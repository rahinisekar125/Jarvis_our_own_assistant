from __future__ import annotations

import logging
import time
from queue import Empty, Full, Queue
from typing import Any

from ..config import AudioSettings

LOGGER = logging.getLogger(__name__)


class CallbackAudioInputStream:
    def __init__(self, settings: AudioSettings) -> None:
        import sounddevice as sd

        self.settings = settings
        self.channels = settings.input_channels
        self.sample_width = 2
        self._queue: Queue[bytes] = Queue(maxsize=96)
        self._buffer = bytearray()
        self._overflowed = False

        def callback(indata: bytes, _frames: int, _time_info: Any, status: Any) -> None:
            if status:
                self._overflowed = True
                LOGGER.debug("Audio input status: %s", status)
            try:
                self._queue.put_nowait(bytes(indata))
            except Full:
                self._overflowed = True

        self._stream = _open_first_working_stream(
            sd=sd,
            settings=settings,
            channels=self.channels,
            callback=callback,
        )

    def start(self) -> None:
        self._stream.start()

    def read(self, frames: int) -> tuple[bytes, bool]:
        target_bytes = frames * self.channels * self.sample_width
        deadline = time.monotonic() + 2.0
        overflowed = self._overflowed
        self._overflowed = False

        while len(self._buffer) < target_bytes:
            timeout = max(0.05, min(0.25, deadline - time.monotonic()))
            try:
                self._buffer.extend(self._queue.get(timeout=timeout))
            except Empty as exc:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Timed out waiting for microphone audio") from exc

        chunk = bytes(self._buffer[:target_bytes])
        del self._buffer[:target_bytes]
        return chunk, overflowed

    def stop(self) -> None:
        self._stream.stop()

    def close(self) -> None:
        self._stream.close()


def _resolve_input_device(sd: Any, configured: str) -> int | str | None:
    value = configured.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        pass

    needle = value.lower()
    for device in sd.query_devices():
        if device.get("max_input_channels", 0) <= 0:
            continue
        name = str(device.get("name", ""))
        if needle in name.lower():
            return int(device["index"])
    return value


def _open_first_working_stream(sd: Any, settings: AudioSettings, channels: int, callback: Any):
    errors: list[str] = []
    candidates = _input_device_candidates(sd, settings.input_device)
    for candidate in candidates:
        try:
            stream = sd.RawInputStream(
                device=candidate,
                samplerate=settings.sample_rate,
                channels=channels,
                dtype="int16",
                blocksize=0,
                callback=callback,
            )
            LOGGER.info(
                "Using audio input device=%s rate=%s channels=%s",
                "default" if candidate is None else candidate,
                settings.sample_rate,
                channels,
            )
            return stream
        except Exception as exc:  # noqa: BLE001 - Windows audio devices often vanish/change ids.
            errors.append(f"{candidate}: {exc}")

    raise RuntimeError("No working microphone input found. Tried: " + "; ".join(errors))


def _input_device_candidates(sd: Any, configured: str) -> list[int | str | None]:
    candidates: list[int | str | None] = []

    def add(candidate: int | str | None) -> None:
        if candidate not in candidates:
            candidates.append(candidate)

    value = configured.strip()
    if value:
        try:
            add(int(value))
        except ValueError:
            resolved = _resolve_input_device(sd, value)
            add(resolved)

    add(None)
    try:
        default_input = sd.default.device[0]
        if default_input is not None and int(default_input) >= 0:
            add(int(default_input))
    except Exception:  # noqa: BLE001 - optional fallback only.
        pass

    for index, device in enumerate(sd.query_devices()):
        if device.get("max_input_channels", 0) > 0:
            add(index)

    return candidates
