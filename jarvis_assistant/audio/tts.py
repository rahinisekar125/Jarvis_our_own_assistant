from __future__ import annotations

import logging
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Callable

from ..config import TTSSettings

LOGGER = logging.getLogger(__name__)


class Speaker:
    def speak(self, text: str) -> None:
        raise NotImplementedError

    def cancel(self) -> None:
        return None


@dataclass(slots=True)
class ConsoleSpeaker(Speaker):
    def speak(self, text: str) -> None:
        print(f"Jarvis> {text}")


class Pyttsx3Speaker(Speaker):
    def __init__(self, settings: TTSSettings) -> None:
        import pyttsx3

        self._engine = pyttsx3.init()
        if settings.voice:
            _select_pyttsx3_voice(self._engine, settings.voice)
        self._engine.setProperty("rate", settings.rate)
        self._engine.setProperty("volume", settings.volume)

    def speak(self, text: str) -> None:
        self._engine.say(text)
        self._engine.runAndWait()

    def cancel(self) -> None:
        try:
            self._engine.stop()
        except Exception:  # noqa: BLE001 - cancellation is best-effort.
            pass


class EdgeTTSSpeaker(Speaker):
    def __init__(self, settings: TTSSettings) -> None:
        import edge_tts  # noqa: F401 - verifies dependency at construction time.

        self.voice = settings.voice or "en-IN-PrabhatNeural"
        self.rate = settings.edge_rate
        self.volume = settings.edge_volume
        self.tmp_dir = Path(tempfile.gettempdir()) / "jarvis_edge_tts"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._active_alias: str | None = None

    def speak(self, text: str) -> None:
        import asyncio
        import edge_tts

        self._cancel_event.clear()
        path = self.tmp_dir / f"jarvis_{uuid.uuid4().hex}.mp3"

        async def save_audio() -> None:
            communicate = edge_tts.Communicate(
                text,
                self.voice,
                rate=self.rate,
                volume=self.volume,
            )
            await communicate.save(str(path))

        asyncio.run(save_audio())
        try:
            if not self._cancel_event.is_set():
                self._play_audio_file_windows(path)
        finally:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                LOGGER.debug("Could not remove temporary TTS file: %s", path)

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            alias = self._active_alias
        if not alias:
            return
        for command in (f"stop {alias}", f"close {alias}"):
            try:
                _mci_send(command)
            except Exception:
                pass

    def _play_audio_file_windows(self, path: Path) -> None:
        if not path.exists() or path.stat().st_size == 0:
            raise RuntimeError(f"TTS audio file was not created: {path}")

        if sys.platform == "win32":
            self._play_with_mci(path)
            return

        raise RuntimeError("Edge TTS playback is currently implemented for Windows paths.")

    def _play_with_mci(self, path: Path) -> None:
        alias = f"jarvis_{uuid.uuid4().hex}"
        opened = False

        try:
            _mci_send(f'open "{path}" type mpegvideo alias {alias}')
            opened = True
            with self._lock:
                if self._cancel_event.is_set():
                    return
                self._active_alias = alias
            _mci_send(f"play {alias} wait")
            time.sleep(0.05)
        finally:
            with self._lock:
                if self._active_alias == alias:
                    self._active_alias = None
            if opened:
                try:
                    _mci_send(f"close {alias}")
                except Exception:
                    pass


class AsyncSpeaker(Speaker):
    def __init__(self, speaker_factory: Callable[[], Speaker], max_queue_size: int = 3) -> None:
        self._speaker_factory = speaker_factory
        self._queue: Queue[str | None] = Queue(maxsize=max_queue_size)
        self._closed = False
        self._speaker: Speaker | None = None
        self._speaker_lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def speak(self, text: str) -> None:
        if self._closed:
            return
        clean_text = text.strip()
        if not clean_text:
            return
        try:
            self._queue.put_nowait(clean_text)
            return
        except Full:
            pass

        try:
            self._queue.get_nowait()
        except Empty:
            pass

        try:
            self._queue.put_nowait(clean_text)
        except Full:
            LOGGER.debug("Dropped queued speech because the speaker is busy")

    def cancel(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except Empty:
                break

        with self._speaker_lock:
            speaker = self._speaker
        if speaker is not None:
            speaker.cancel()

    def close(self, wait: bool = False) -> None:
        self._closed = True
        try:
            self._queue.put_nowait(None)
        except Full:
            pass
        if wait:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        try:
            speaker = self._speaker_factory()
        except Exception as exc:  # noqa: BLE001 - voice mode should continue without TTS.
            LOGGER.warning("Async TTS unavailable, using console output: %s", exc)
            speaker = ConsoleSpeaker()
        with self._speaker_lock:
            self._speaker = speaker

        while True:
            text = self._queue.get()
            if text is None:
                return
            try:
                speaker.speak(text)
            except Exception as exc:  # noqa: BLE001 - one bad utterance must not kill the voice loop.
                LOGGER.warning("Speech output failed: %s", exc)


def create_speaker(settings: TTSSettings) -> Speaker:
    if not settings.enabled:
        return ConsoleSpeaker()
    if settings.backend == "edge":
        try:
            return EdgeTTSSpeaker(settings)
        except Exception as exc:  # noqa: BLE001 - local voice fallback keeps Jarvis usable.
            LOGGER.warning("Edge TTS unavailable, falling back to pyttsx3: %s", exc)
    try:
        return Pyttsx3Speaker(settings)
    except Exception as exc:  # noqa: BLE001 - console fallback is safer than crashing.
        LOGGER.warning("TTS unavailable, using console output: %s", exc)
        return ConsoleSpeaker()


def create_async_speaker(settings: TTSSettings) -> Speaker:
    return AsyncSpeaker(lambda: create_speaker(settings))


def _select_pyttsx3_voice(engine, preferred: str) -> None:
    preferred_lower = preferred.lower()
    for voice in engine.getProperty("voices") or []:
        voice_id = str(getattr(voice, "id", ""))
        voice_name = str(getattr(voice, "name", ""))
        languages = " ".join(str(item) for item in getattr(voice, "languages", []) or [])
        haystack = " ".join([voice_id, voice_name, languages]).lower()
        if preferred_lower in haystack or "en-in" in haystack or "india" in haystack:
            engine.setProperty("voice", voice_id)
            LOGGER.info("Using pyttsx3 voice=%s", voice_name or voice_id)
            return
    LOGGER.warning("Preferred pyttsx3 voice not found: %s", preferred)


def _mci_send(command: str) -> None:
    import ctypes

    winmm = ctypes.WinDLL("winmm")
    buffer = ctypes.create_unicode_buffer(512)
    error = winmm.mciSendStringW(command, buffer, len(buffer), None)
    if error:
        error_text = ctypes.create_unicode_buffer(512)
        winmm.mciGetErrorStringW(error, error_text, len(error_text))
        raise RuntimeError(f"MCI audio command failed: {error_text.value or error}")
