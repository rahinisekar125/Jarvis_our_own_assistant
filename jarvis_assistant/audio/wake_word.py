from __future__ import annotations

import json
import logging
import sys
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from ..config import AudioSettings
from .input_stream import CallbackAudioInputStream
from .vosk_model import get_vosk_model
from .whisper_model import get_whisper_model

LOGGER = logging.getLogger(__name__)
CANCEL_PHRASES = ("quit",)


class WakeWordDetector:
    def wait_for_wake_word(self) -> str:
        raise NotImplementedError


@dataclass(slots=True)
class KeyboardWakeWordDetector(WakeWordDetector):
    prompt: str = "Press Enter to simulate wake word..."

    def wait_for_wake_word(self) -> str:
        input(self.prompt)
        return "wake"


class PorcupineWakeWordDetector(WakeWordDetector):
    def __init__(self, settings: AudioSettings) -> None:
        try:
            import pvporcupine
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError("pvporcupine and sounddevice are required for wake word mode") from exc

        if not settings.picovoice_access_key:
            raise RuntimeError("PICOVOICE_ACCESS_KEY is required for Porcupine wake word mode")

        keyword_path = settings.porcupine_keyword_path.strip()
        if keyword_path:
            keyword_paths = [str(Path(keyword_path).expanduser())]
            keywords = None
        else:
            keyword_paths = None
            keywords = ["jarvis"]
            LOGGER.warning(
                "PORCUPINE_KEYWORD_PATH not set. Using built-in 'jarvis'. "
                "Use a custom .ppn model for the exact phrase 'Hey Jarvis'."
            )

        self._sd = sd
        self._porcupine = pvporcupine.create(
            access_key=settings.picovoice_access_key,
            keyword_paths=keyword_paths,
            keywords=keywords,
        )
        self._stream = sd.RawInputStream(
            samplerate=self._porcupine.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=self._porcupine.frame_length,
        )
        self._stream.start()

    def wait_for_wake_word(self) -> str:
        while True:
            data, overflowed = self._stream.read(self._porcupine.frame_length)
            if overflowed:
                LOGGER.debug("Wake-word audio input overflowed")
            frame = memoryview(data).cast("h")
            if self._porcupine.process(frame) >= 0:
                return "wake"

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()
        self._porcupine.delete()


class SapiWakeWordDetector(WakeWordDetector):
    def __init__(self, settings: AudioSettings) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Windows SAPI wake mode is only available on Windows")
        try:
            import pythoncom
            import win32com.client
        except ImportError as exc:
            raise RuntimeError("pywin32 is required for Windows SAPI wake mode") from exc

        self.settings = settings
        self._pythoncom = pythoncom
        self._wake_event = threading.Event()
        self._event_type = "wake"
        self._aliases = _wake_aliases(settings)

        def on_recognition(_event_self, _stream_number, _stream_position, _recognition_type, result):
            text = _normalize(result.PhraseInfo.GetText())
            self._event_type = "cancel" if _has_cancel_phrase(text) else "wake"
            LOGGER.info("SAPI voice event detected type=%s text=%s", self._event_type, text)
            self._wake_event.set()

        event_class = type(
            "SapiWakeEvents",
            (),
            {
                "OnRecognition": on_recognition,
            },
        )

        pythoncom.CoInitialize()
        self._context = win32com.client.DispatchWithEvents("SAPI.SpSharedRecoContext", event_class)
        self._grammar = self._context.CreateGrammar(0)
        self._grammar.DictationSetState(0)
        self._rule_name = "JarvisWakeRule"
        rule = self._grammar.Rules.Add(self._rule_name, 1 | 32, 0)
        for alias in [*self._aliases, *CANCEL_PHRASES]:
            rule.InitialState.AddWordTransition(None, alias)
        self._grammar.Rules.Commit()
        self._active = False

    def wait_for_wake_word(self) -> str:
        self._wake_event.clear()
        self._event_type = "wake"
        self._set_active(True)
        try:
            while not self._wake_event.is_set():
                self._pythoncom.PumpWaitingMessages()
                time.sleep(0.02)
            return self._event_type
        finally:
            self._set_active(False)

    def close(self) -> None:
        self._set_active(False)

    def _set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._grammar.CmdSetRuleState(self._rule_name, 1 if active else 0)
        self._active = active


class VoskWakeWordDetector(WakeWordDetector):
    def __init__(self, settings: AudioSettings) -> None:
        try:
            from vosk import KaldiRecognizer
        except ImportError as exc:
            raise RuntimeError("vosk is required for Vosk wake mode") from exc

        self.settings = settings
        self._recognizer_cls = KaldiRecognizer
        self._model = get_vosk_model(settings.wake_vosk_model_path)
        self._aliases = _wake_aliases(settings)
        self._grammar = json.dumps([*self._aliases, *CANCEL_PHRASES, "[unk]"])
        self._frame_size = max(1, int(settings.sample_rate * max(0.03, settings.frame_ms / 1000)))

    def wait_for_wake_word(self) -> str:
        recognizer = self._recognizer_cls(
            self._model,
            float(self.settings.sample_rate),
            self._grammar,
        )
        stream = CallbackAudioInputStream(self.settings)
        stream.start()
        try:
            while True:
                chunk, overflowed = stream.read(self._frame_size)
                if overflowed:
                    LOGGER.debug("Vosk wake audio input overflowed")

                if recognizer.AcceptWaveform(chunk):
                    text = str(json.loads(recognizer.Result()).get("text", ""))
                else:
                    text = str(json.loads(recognizer.PartialResult()).get("partial", ""))

                if _has_wake_phrase(text, self._aliases):
                    LOGGER.info("Vosk wake word detected text=%s", text)
                    return "wake"
                if _has_cancel_phrase(text):
                    LOGGER.info("Vosk cancel word detected text=%s", text)
                    return "cancel"
        finally:
            try:
                stream.stop()
            finally:
                stream.close()


class WhisperWakeWordDetector(WakeWordDetector):
    def __init__(self, settings: AudioSettings, tmp_dir: Path) -> None:
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError("sounddevice and faster-whisper are required for Whisper wake mode") from exc

        self.settings = settings
        self.tmp_dir = tmp_dir
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self._frame_size = int(settings.sample_rate * settings.frame_ms / 1000)
        self._stream = CallbackAudioInputStream(settings)
        self._stream.start()
        try:
            self._model = get_whisper_model(
                settings.wake_whisper_model,
                settings.whisper_device,
                settings.whisper_compute_type,
            )
        except Exception:
            self.close()
            raise

    def wait_for_wake_word(self) -> str:
        phrase = _normalize(self.settings.wake_word_phrase)
        while True:
            wav_path, level = self._record_snippet()
            if level < self.settings.wake_energy_threshold:
                try:
                    wav_path.unlink(missing_ok=True)
                except OSError:
                    LOGGER.debug("Could not remove quiet wake temp wav: %s", wav_path)
                time.sleep(self.settings.whisper_wake_cooldown_seconds)
                continue
            try:
                segments, _info = self._model.transcribe(
                    str(wav_path),
                    beam_size=1,
                    vad_filter=False,
                    condition_on_previous_text=False,
                    language="en",
                )
                text = _normalize(" ".join(segment.text for segment in segments))
                if phrase in text:
                    LOGGER.info("Whisper wake word detected text=%s", text)
                    return "wake"
                if _has_cancel_phrase(text):
                    LOGGER.info("Whisper cancel word detected text=%s", text)
                    return "cancel"
            finally:
                try:
                    wav_path.unlink(missing_ok=True)
                except OSError:
                    LOGGER.debug("Could not remove wake temp wav: %s", wav_path)
            time.sleep(self.settings.whisper_wake_cooldown_seconds)

    def _record_snippet(self) -> tuple[Path, int]:
        target_frames = int(self.settings.sample_rate * self.settings.whisper_wake_seconds)
        remaining = target_frames
        chunks: list[bytes] = []
        while remaining > 0:
            read_frames = min(self._frame_size, remaining)
            chunk, overflowed = self._stream.read(read_frames)
            if overflowed:
                LOGGER.debug("Wake audio input overflowed")
            chunks.append(bytes(chunk))
            remaining -= read_frames

        with NamedTemporaryFile(
            suffix=".wav",
            prefix="jarvis_wake_",
            dir=self.tmp_dir,
            delete=False,
        ) as temp:
            wav_path = Path(temp.name)

        data_bytes = b"".join(chunks)
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(self.settings.input_channels)
            wf.setsampwidth(2)
            wf.setframerate(self.settings.sample_rate)
            wf.writeframes(data_bytes)

        return wav_path, _rms_int16(data_bytes)

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()


class RetryingWakeWordDetector(WakeWordDetector):
    def __init__(self, settings: AudioSettings, tmp_dir: Path, retry_seconds: float = 2.0) -> None:
        self.settings = settings
        self.tmp_dir = tmp_dir
        self.retry_seconds = retry_seconds
        self._detector: WakeWordDetector | None = None

    def wait_for_wake_word(self) -> str:
        while True:
            if self._detector is None:
                self._detector = self._create_detector()

            try:
                return self._detector.wait_for_wake_word()
            except Exception as exc:  # noqa: BLE001 - audio devices can disappear/reappear on Windows.
                LOGGER.warning(
                    "Wake detector failed; reinitializing in %.1fs: %s",
                    self.retry_seconds,
                    exc,
                    exc_info=True,
                )
                self._close_detector()
                time.sleep(self.retry_seconds)

    def close(self) -> None:
        self._close_detector()

    def _create_detector(self) -> WakeWordDetector:
        while True:
            try:
                return _create_live_wake_detector(self.settings, self.tmp_dir)
            except Exception as exc:  # noqa: BLE001 - keep hidden/background mode alive.
                LOGGER.warning(
                    "Wake detector unavailable; retrying in %.1fs: %s",
                    self.retry_seconds,
                    exc,
                    exc_info=True,
                )
                time.sleep(self.retry_seconds)

    def _close_detector(self) -> None:
        detector = self._detector
        self._detector = None
        close = getattr(detector, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001 - shutdown cleanup should not crash the voice loop.
                LOGGER.debug("Wake detector close failed", exc_info=True)


def create_wake_word_detector(
    settings: AudioSettings,
    tmp_dir: Path,
    *,
    allow_keyboard_fallback: bool = False,
) -> WakeWordDetector:
    if not allow_keyboard_fallback:
        return RetryingWakeWordDetector(settings, tmp_dir)

    try:
        return _create_live_wake_detector(settings, tmp_dir)
    except Exception as exc:  # noqa: BLE001 - explicit dev-shell fallback only.
        LOGGER.warning("Wake detector unavailable, falling back to keyboard trigger: %s", exc, exc_info=True)
        return KeyboardWakeWordDetector()


def _create_live_wake_detector(settings: AudioSettings, tmp_dir: Path) -> WakeWordDetector:
    engine = settings.wake_engine.lower().strip() or "auto"
    if engine in {"vosk", "auto"}:
        try:
            LOGGER.info("Using Vosk wake engine aliases=%s", _wake_aliases(settings))
            return VoskWakeWordDetector(settings)
        except Exception as exc:  # noqa: BLE001 - fall through to other wake engines.
            if engine == "vosk":
                raise
            LOGGER.warning("Vosk wake word unavailable, trying next wake engine: %s", exc, exc_info=True)

    if engine in {"sapi", "auto"}:
        try:
            LOGGER.info("Using Windows SAPI wake engine aliases=%s", _wake_aliases(settings))
            return SapiWakeWordDetector(settings)
        except Exception as exc:  # noqa: BLE001 - fall through to other wake engines.
            if engine == "sapi":
                raise
            LOGGER.warning("SAPI wake word unavailable, trying next wake engine: %s", exc, exc_info=True)

    if engine in {"porcupine", "auto"} and settings.picovoice_access_key:
        try:
            return PorcupineWakeWordDetector(settings)
        except Exception as exc:  # noqa: BLE001 - Whisper keeps the assistant usable.
            LOGGER.warning("Porcupine wake word unavailable, using Whisper wake mode: %s", exc, exc_info=True)
    elif engine == "porcupine":
        raise RuntimeError("PICOVOICE_ACCESS_KEY is required for Porcupine wake word mode")

    LOGGER.info("Using Whisper wake engine")
    return WhisperWakeWordDetector(settings, tmp_dir)


def _wake_aliases(settings: AudioSettings) -> list[str]:
    aliases = [
        item.strip().lower()
        for item in settings.wake_aliases.split(";")
        if item.strip()
    ]
    phrase = settings.wake_word_phrase.strip().lower()
    if phrase and phrase not in aliases:
        aliases.insert(0, phrase)
    return aliases or ["hey jarvis"]


def _has_wake_phrase(text: str, aliases: list[str]) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False
    return any(_normalize(alias) in normalized for alias in aliases)


def _has_cancel_phrase(text: str) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False
    tokens = set(normalized.split())
    return any(_normalize(phrase) in tokens for phrase in CANCEL_PHRASES)


def _normalize(text: str) -> str:
    return " ".join(
        "".join(char.lower() if char.isalnum() or char.isspace() else " " for char in text).split()
    )


def _rms_int16(frame: bytes) -> int:
    samples = memoryview(frame).cast("h")
    if len(samples) == 0:
        return 0
    total = sum(sample * sample for sample in samples)
    return int((total / len(samples)) ** 0.5)
