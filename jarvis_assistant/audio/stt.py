from __future__ import annotations

import json
import logging
import time
import wave
from collections import deque
from pathlib import Path
from tempfile import NamedTemporaryFile

from ..config import AudioSettings
from .input_stream import CallbackAudioInputStream
from .vosk_model import get_vosk_model
from .whisper_model import get_whisper_model

LOGGER = logging.getLogger(__name__)


class FasterWhisperTranscriber:
    def __init__(self, settings: AudioSettings, tmp_dir: Path) -> None:
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError("sounddevice and faster-whisper are required for speech recognition") from exc

        self.settings = settings
        self.tmp_dir = tmp_dir
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self._model = get_whisper_model(
            settings.whisper_model,
            settings.whisper_device,
            settings.whisper_compute_type,
        )
        self._warm_model()

    def listen_and_transcribe(self) -> str:
        wav_path = self._record_until_silence()
        try:
            segments, info = self._model.transcribe(
                str(wav_path),
                beam_size=1,
                best_of=1,
                temperature=0.0,
                vad_filter=False,
                condition_on_previous_text=False,
                language=_whisper_language(self.settings),
                initial_prompt=self.settings.whisper_initial_prompt.strip() or None,
                hotwords=self.settings.whisper_hotwords.strip() or None,
                without_timestamps=True,
                no_speech_threshold=0.5,
                log_prob_threshold=-0.8,
                hallucination_silence_threshold=1.0,
                language_detection_segments=1,
            )
            segment_list = list(segments)
            text = " ".join(segment.text.strip() for segment in segment_list).strip()
            if _is_low_confidence_whisper_text(segment_list, text):
                LOGGER.info("Whisper command ignored low-confidence/no-speech text=%s", text)
                return ""
            LOGGER.info(
                "Whisper command transcribed language=%s probability=%.2f text=%s",
                getattr(info, "language", "unknown"),
                float(getattr(info, "language_probability", 0.0) or 0.0),
                text,
            )
            return text
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except OSError:
                LOGGER.debug("Could not remove temp wav: %s", wav_path)

    def _record_until_silence(self) -> Path:
        frame_size = int(self.settings.sample_rate * self.settings.frame_ms / 1000)
        stream = CallbackAudioInputStream(self.settings)
        stream.start()

        frames: list[bytes] = []
        pre_roll_frames = max(1, int(0.35 / (self.settings.frame_ms / 1000)))
        pre_roll: deque[bytes] = deque(maxlen=pre_roll_frames)
        noise_levels: deque[int] = deque(maxlen=max(6, int(0.8 / (self.settings.frame_ms / 1000))))
        started = False
        loud_run = 0
        silence_started_at: float | None = None
        start_time = time.monotonic()

        sample_width = 2
        try:
            while True:
                chunk, overflowed = stream.read(frame_size)
                if overflowed:
                    LOGGER.debug("Speech audio input overflowed")
                chunk_bytes = bytes(chunk)
                level = _rms_int16(chunk_bytes)
                now = time.monotonic()
                threshold = _adaptive_threshold(noise_levels, self.settings.energy_threshold)

                if not started:
                    pre_roll.append(chunk_bytes)
                    if level >= threshold:
                        loud_run += 1
                    else:
                        loud_run = 0
                        noise_levels.append(level)

                    if loud_run >= 2:
                        started = True
                        silence_started_at = None
                        frames.extend(pre_roll)
                    else:
                        if now - start_time >= self.settings.speech_start_timeout_seconds:
                            break

                        if now - start_time >= self.settings.max_record_seconds:
                            break
                    continue

                if level >= threshold:
                    silence_started_at = None
                    frames.append(chunk_bytes)
                elif started and silence_started_at is None:
                    silence_started_at = now
                    frames.append(chunk_bytes)
                elif started:
                    frames.append(chunk_bytes)

                if started and silence_started_at is not None:
                    if now - silence_started_at >= self.settings.silence_seconds:
                        break

                if not started and now - start_time >= self.settings.speech_start_timeout_seconds:
                    break

                if now - start_time >= self.settings.max_record_seconds:
                    break
        finally:
            stream.stop()
            stream.close()

        if not frames:
            frames.extend(pre_roll)

        with NamedTemporaryFile(
            suffix=".wav",
            prefix="jarvis_",
            dir=self.tmp_dir,
            delete=False,
        ) as temp:
            wav_path = Path(temp.name)

        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(self.settings.input_channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(self.settings.sample_rate)
            wf.writeframes(b"".join(frames))

        return wav_path

    def _warm_model(self) -> None:
        with NamedTemporaryFile(
            suffix=".wav",
            prefix="jarvis_warmup_",
            dir=self.tmp_dir,
            delete=False,
        ) as temp:
            wav_path = Path(temp.name)

        try:
            with wave.open(str(wav_path), "wb") as wf:
                wf.setnchannels(self.settings.input_channels)
                wf.setsampwidth(2)
                wf.setframerate(self.settings.sample_rate)
                silent_frames = int(self.settings.sample_rate * 0.2)
                wf.writeframes(b"\0" * silent_frames * self.settings.input_channels * 2)

            segments, _info = self._model.transcribe(
                str(wav_path),
                beam_size=1,
                best_of=1,
                temperature=0.0,
                vad_filter=False,
                condition_on_previous_text=False,
                language=_whisper_language(self.settings),
                without_timestamps=True,
                no_speech_threshold=0.5,
                language_detection_segments=1,
            )
            for _segment in segments:
                pass
            LOGGER.info("Whisper command model warmed")
        except Exception as exc:  # noqa: BLE001 - warmup is only a responsiveness optimization.
            LOGGER.debug("Whisper command model warmup skipped: %s", exc, exc_info=True)
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except OSError:
                LOGGER.debug("Could not remove warmup wav: %s", wav_path)


def _rms_int16(frame: bytes) -> int:
    samples = memoryview(frame).cast("h")
    if len(samples) == 0:
        return 0
    total = sum(sample * sample for sample in samples)
    return int((total / len(samples)) ** 0.5)


def _adaptive_threshold(noise_levels: deque[int], minimum: int) -> int:
    if len(noise_levels) < 4:
        return minimum
    ordered = sorted(noise_levels)
    median = ordered[len(ordered) // 2]
    return max(minimum, int(median * 2.8), median + 35)


def _is_low_confidence_whisper_text(segments: list[object], text: str) -> bool:
    if not text.strip() or not segments:
        return False
    avg_log_probs = [
        float(value)
        for value in (getattr(segment, "avg_logprob", None) for segment in segments)
        if value is not None
    ]
    no_speech_probs = [
        float(value)
        for value in (getattr(segment, "no_speech_prob", None) for segment in segments)
        if value is not None
    ]
    avg_log_prob = sum(avg_log_probs) / len(avg_log_probs) if avg_log_probs else 0.0
    max_no_speech = max(no_speech_probs) if no_speech_probs else 0.0
    return max_no_speech >= 0.85 and avg_log_prob <= -0.8


class VoskTranscriber:
    def __init__(self, settings: AudioSettings, tmp_dir: Path | None = None) -> None:
        try:
            from vosk import KaldiRecognizer
        except ImportError as exc:
            raise RuntimeError("vosk is required for fast speech recognition") from exc

        self.settings = settings
        self._recognizer_cls = KaldiRecognizer
        self._model = get_vosk_model(settings.wake_vosk_model_path)
        self._frame_size = max(1, int(settings.sample_rate * 0.08))

    def listen_and_transcribe(self) -> str:
        recognizer = self._recognizer_cls(self._model, float(self.settings.sample_rate))
        _enable_word_confidence(recognizer)
        stream = CallbackAudioInputStream(self.settings)
        stream.start()

        started = False
        start_time = time.monotonic()
        silence_started_at: float | None = None
        last_partial = ""
        final_parts: list[str] = []
        final_payloads: list[dict] = []

        try:
            while True:
                chunk, overflowed = stream.read(self._frame_size)
                if overflowed:
                    LOGGER.debug("Vosk speech audio input overflowed")

                level = _rms_int16(chunk)
                now = time.monotonic()

                if recognizer.AcceptWaveform(chunk):
                    payload = json.loads(recognizer.Result())
                    text = str(payload.get("text", "")).strip()
                    if text:
                        final_parts.append(text)
                        final_payloads.append(payload)
                        started = True
                        silence_started_at = now
                else:
                    partial = str(json.loads(recognizer.PartialResult()).get("partial", "")).strip()
                    if partial:
                        last_partial = partial
                        started = True
                        silence_started_at = None

                if level >= self.settings.energy_threshold:
                    started = True
                    silence_started_at = None
                elif started and silence_started_at is None:
                    silence_started_at = now

                if started and silence_started_at is not None:
                    if now - silence_started_at >= self.settings.silence_seconds:
                        break

                if not started and now - start_time >= self.settings.speech_start_timeout_seconds:
                    break

                if now - start_time >= self.settings.max_record_seconds:
                    break
        finally:
            try:
                stream.stop()
            finally:
                stream.close()

        final_payload = json.loads(recognizer.FinalResult())
        final_text = str(final_payload.get("text", "")).strip()
        if final_text:
            final_parts.append(final_text)
            final_payloads.append(final_payload)

        text = " ".join(part for part in final_parts if part).strip()
        if not text:
            text = last_partial.strip()
        confidence = _average_word_confidence(final_payloads)
        if text and confidence is not None and confidence < self.settings.stt_min_confidence:
            LOGGER.info(
                "Vosk command ignored low-confidence text=%s confidence=%.2f threshold=%.2f",
                text,
                confidence,
                self.settings.stt_min_confidence,
            )
            return ""
        LOGGER.info("Vosk command transcribed text=%s", text)
        return text


def create_transcriber(settings: AudioSettings, tmp_dir: Path):
    if settings.stt_engine == "vosk":
        return VoskTranscriber(settings, tmp_dir)
    if settings.stt_engine == "whisper":
        return FasterWhisperTranscriber(settings, tmp_dir)
    raise ValueError(f"Unsupported STT engine: {settings.stt_engine}")


def _whisper_language(settings: AudioSettings) -> str | None:
    language = settings.whisper_language.strip().lower()
    if language in {"", "auto", "detect"}:
        return None
    return language


def _enable_word_confidence(recognizer) -> None:
    set_words = getattr(recognizer, "SetWords", None)
    if callable(set_words):
        set_words(True)


def _average_word_confidence(payloads: list[dict]) -> float | None:
    values: list[float] = []
    for payload in payloads:
        for item in payload.get("result", []) or []:
            if "conf" in item:
                values.append(float(item["conf"]))
    if not values:
        return None
    return sum(values) / len(values)
