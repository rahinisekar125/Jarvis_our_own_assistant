from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - setup environments may not have deps yet.
    yaml = None

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - setup environments may not have deps yet.
    def load_dotenv() -> None:
        return None


@dataclass(slots=True)
class AssistantSettings:
    name: str = "Jarvis"
    max_tool_rounds: int = 5


@dataclass(slots=True)
class LLMSettings:
    provider: str = "gemini"
    temperature: float = 0.2
    timeout_seconds: int = 45
    max_retries: int = 5
    retry_base_delay_seconds: float = 2.0
    retry_max_delay_seconds: float = 30.0
    cooldown_seconds: float = 1.0
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout_seconds: int = 60
    ollama_max_retries: int = 1
    ollama_backup_enabled: bool = True
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    voice_provider: str = "ollama"
    voice_timeout_seconds: int = 12
    voice_max_retries: int = 1
    voice_retry_base_delay_seconds: float = 0.5
    voice_cooldown_seconds: float = 0.0
    voice_ollama_backup_enabled: bool = False


@dataclass(slots=True)
class AudioSettings:
    sample_rate: int = 16000
    frame_ms: int = 30
    input_device: str = ""
    input_channels: int = 1
    wake_engine: str = "vosk"
    wake_aliases: str = "hey jarvis"
    wake_vosk_model_path: str = "models/vosk-model-small-en-us-0.15"
    stt_engine: str = "vosk"
    stt_min_confidence: float = 0.6
    speak_wake_greeting: bool = False
    silence_seconds: float = 0.75
    max_record_seconds: float = 12.0
    speech_start_timeout_seconds: float = 5.0
    energy_threshold: int = 380
    wake_word_phrase: str = "hey jarvis"
    wake_greeting: str = "hi Ayush tell me something what you want"
    whisper_wake_seconds: float = 1.6
    whisper_wake_cooldown_seconds: float = 0.05
    wake_energy_threshold: int = 180
    wake_whisper_model: str = "tiny.en"
    whisper_model: str = "base.en"
    whisper_language: str = "en"
    whisper_initial_prompt: str = ""
    whisper_hotwords: str = ""
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    picovoice_access_key: str = ""
    porcupine_keyword_path: str = ""


@dataclass(slots=True)
class TTSSettings:
    enabled: bool = True
    backend: str = "pyttsx3"
    voice: str = ""
    rate: int = 185
    volume: float = 1.0
    edge_rate: str = "+0%"
    edge_volume: str = "+0%"


@dataclass(slots=True)
class VisualSettings:
    enabled: bool = True
    always_on_top: bool = True
    width: int = 520
    height: int = 320
    duration_seconds: float = 45.0
    show_startup: bool = False
    show_wake: bool = False
    show_heard: bool = False
    show_final: bool = True


@dataclass(slots=True)
class SecuritySettings:
    allowed_paths: list[Path] = field(default_factory=list)
    command_timeout_seconds: int = 60
    file_read_limit_bytes: int = 200_000
    require_confirmation_for_shell: bool = False


@dataclass(slots=True)
class MemorySettings:
    db_path: Path = Path("data/memory.sqlite3")


@dataclass(slots=True)
class Settings:
    base_dir: Path
    data_dir: Path
    assistant: AssistantSettings
    llm: LLMSettings
    audio: AudioSettings
    tts: TTSSettings
    visual: VisualSettings
    security: SecuritySettings
    memory: MemorySettings


def load_settings(config_path: str | None = None) -> Settings:
    load_dotenv()

    base_dir = Path(os.getenv("JARVIS_BASE_DIR", Path.cwd())).expanduser().resolve()
    config_file = Path(config_path or os.getenv("JARVIS_CONFIG", "config.yaml"))
    if not config_file.is_absolute():
        config_file = base_dir / config_file

    raw = _load_yaml(config_file)

    data_dir = Path(os.getenv("JARVIS_DATA_DIR", raw.get("data_dir", "data"))).expanduser()
    if not data_dir.is_absolute():
        data_dir = base_dir / data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    assistant_raw = raw.get("assistant", {})
    llm_raw = raw.get("llm", {})
    audio_raw = raw.get("audio", {})
    tts_raw = raw.get("tts", {})
    visual_raw = raw.get("visual", {})
    security_raw = raw.get("security", {})

    allowed_paths = _resolve_allowed_paths(
        base_dir=base_dir,
        configured=security_raw.get("allowed_paths", []),
        env_value=os.getenv("JARVIS_ALLOWED_PATHS", ""),
    )

    assistant = AssistantSettings(
        name=str(assistant_raw.get("name", "Jarvis")),
        max_tool_rounds=int(assistant_raw.get("max_tool_rounds", 5)),
    )

    llm = LLMSettings(
        provider=os.getenv("JARVIS_LLM_PROVIDER", llm_raw.get("provider", "gemini")).lower(),
        temperature=float(llm_raw.get("temperature", 0.2)),
        timeout_seconds=int(os.getenv("JARVIS_LLM_TIMEOUT_SECONDS", llm_raw.get("timeout_seconds", 45))),
        max_retries=int(os.getenv("JARVIS_LLM_MAX_RETRIES", llm_raw.get("max_retries", 5))),
        retry_base_delay_seconds=float(
            os.getenv(
                "JARVIS_LLM_RETRY_BASE_DELAY_SECONDS",
                llm_raw.get("retry_base_delay_seconds", 2.0),
            )
        ),
        retry_max_delay_seconds=float(
            os.getenv(
                "JARVIS_LLM_RETRY_MAX_DELAY_SECONDS",
                llm_raw.get("retry_max_delay_seconds", 30.0),
            )
        ),
        cooldown_seconds=float(
            os.getenv("JARVIS_LLM_COOLDOWN_SECONDS", llm_raw.get("cooldown_seconds", 1.0))
        ),
        ollama_base_url=os.getenv(
            "OLLAMA_BASE_URL",
            llm_raw.get("ollama", {}).get("base_url", "http://localhost:11434"),
        ).rstrip("/"),
        ollama_model=os.getenv(
            "OLLAMA_MODEL",
            llm_raw.get("ollama", {}).get("model", "llama3.1:8b"),
        ),
        ollama_timeout_seconds=int(
            os.getenv(
                "JARVIS_OLLAMA_TIMEOUT_SECONDS",
                llm_raw.get("ollama", {}).get("timeout_seconds", 60),
            )
        ),
        ollama_max_retries=int(
            os.getenv(
                "JARVIS_OLLAMA_MAX_RETRIES",
                llm_raw.get("ollama", {}).get("max_retries", 1),
            )
        ),
        ollama_backup_enabled=_env_bool(
            "JARVIS_OLLAMA_BACKUP",
            llm_raw.get("ollama_backup_enabled", True),
        ),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv(
            "MODEL",
            os.getenv(
                "GEMINI_MODEL",
                llm_raw.get("gemini", {}).get("model", "gemini-2.5-flash"),
            ),
        ),
        voice_provider=os.getenv(
            "JARVIS_VOICE_LLM_PROVIDER",
            llm_raw.get("voice_provider", "ollama"),
        ).lower(),
        voice_timeout_seconds=int(
            os.getenv("JARVIS_VOICE_LLM_TIMEOUT_SECONDS", llm_raw.get("voice_timeout_seconds", 12))
        ),
        voice_max_retries=int(
            os.getenv("JARVIS_VOICE_LLM_MAX_RETRIES", llm_raw.get("voice_max_retries", 1))
        ),
        voice_retry_base_delay_seconds=float(
            os.getenv(
                "JARVIS_VOICE_LLM_RETRY_BASE_DELAY_SECONDS",
                llm_raw.get("voice_retry_base_delay_seconds", 0.5),
            )
        ),
        voice_cooldown_seconds=float(
            os.getenv("JARVIS_VOICE_LLM_COOLDOWN_SECONDS", llm_raw.get("voice_cooldown_seconds", 0.0))
        ),
        voice_ollama_backup_enabled=_env_bool(
            "JARVIS_VOICE_OLLAMA_BACKUP",
            llm_raw.get("voice_ollama_backup_enabled", False),
        ),
    )

    audio = AudioSettings(
        sample_rate=int(os.getenv("JARVIS_SAMPLE_RATE", audio_raw.get("sample_rate", 16000))),
        frame_ms=int(audio_raw.get("frame_ms", 30)),
        input_device=os.getenv("JARVIS_INPUT_DEVICE", audio_raw.get("input_device", "")),
        input_channels=int(os.getenv("JARVIS_INPUT_CHANNELS", audio_raw.get("input_channels", 1))),
        wake_engine=os.getenv("JARVIS_WAKE_ENGINE", audio_raw.get("wake_engine", "vosk")).lower(),
        wake_aliases=os.getenv(
            "JARVIS_WAKE_ALIASES",
            audio_raw.get("wake_aliases", "hey jarvis"),
        ),
        wake_vosk_model_path=os.getenv(
            "JARVIS_VOSK_MODEL_PATH",
            audio_raw.get("wake_vosk_model_path", "models/vosk-model-small-en-us-0.15"),
        ),
        stt_engine=os.getenv("JARVIS_STT_ENGINE", audio_raw.get("stt_engine", "vosk")).lower(),
        stt_min_confidence=float(
            os.getenv("JARVIS_STT_MIN_CONFIDENCE", audio_raw.get("stt_min_confidence", 0.6))
        ),
        speak_wake_greeting=_env_bool(
            "JARVIS_SPEAK_WAKE_GREETING",
            audio_raw.get("speak_wake_greeting", False),
        ),
        silence_seconds=float(os.getenv("JARVIS_SILENCE_SECONDS", audio_raw.get("silence_seconds", 0.75))),
        max_record_seconds=float(
            os.getenv("JARVIS_MAX_RECORD_SECONDS", audio_raw.get("max_record_seconds", 12))
        ),
        speech_start_timeout_seconds=float(
            os.getenv(
                "JARVIS_SPEECH_START_TIMEOUT_SECONDS",
                audio_raw.get("speech_start_timeout_seconds", 5),
            )
        ),
        energy_threshold=int(os.getenv("JARVIS_ENERGY_THRESHOLD", audio_raw.get("energy_threshold", 380))),
        wake_word_phrase=os.getenv(
            "JARVIS_WAKE_WORD",
            audio_raw.get("wake_word_phrase", "hey jarvis"),
        ).lower(),
        wake_greeting=os.getenv(
            "JARVIS_WAKE_GREETING",
            audio_raw.get("wake_greeting", "hi Ayush tell me something what you want"),
        ),
        whisper_wake_seconds=float(
            os.getenv(
                "JARVIS_WHISPER_WAKE_SECONDS",
                audio_raw.get("whisper_wake_seconds", 1.6),
            )
        ),
        whisper_wake_cooldown_seconds=float(
            os.getenv(
                "JARVIS_WHISPER_WAKE_COOLDOWN_SECONDS",
                audio_raw.get("whisper_wake_cooldown_seconds", 0.05),
            )
        ),
        wake_energy_threshold=int(
            os.getenv("JARVIS_WAKE_ENERGY_THRESHOLD", audio_raw.get("wake_energy_threshold", 180))
        ),
        wake_whisper_model=os.getenv(
            "JARVIS_WAKE_WHISPER_MODEL",
            audio_raw.get("wake_whisper_model", "tiny.en"),
        ),
        whisper_model=os.getenv("WHISPER_MODEL", audio_raw.get("whisper_model", "base.en")),
        whisper_language=os.getenv("WHISPER_LANGUAGE", audio_raw.get("whisper_language", "en")).lower(),
        whisper_initial_prompt=os.getenv(
            "WHISPER_INITIAL_PROMPT",
            audio_raw.get("whisper_initial_prompt", ""),
        ),
        whisper_hotwords=os.getenv(
            "WHISPER_HOTWORDS",
            audio_raw.get("whisper_hotwords", ""),
        ),
        whisper_device=os.getenv("WHISPER_DEVICE", audio_raw.get("whisper_device", "cpu")),
        whisper_compute_type=os.getenv(
            "WHISPER_COMPUTE_TYPE",
            audio_raw.get("whisper_compute_type", "int8"),
        ),
        picovoice_access_key=os.getenv("PICOVOICE_ACCESS_KEY", ""),
        porcupine_keyword_path=os.getenv("PORCUPINE_KEYWORD_PATH", ""),
    )

    tts = TTSSettings(
        enabled=bool(tts_raw.get("enabled", True)),
        backend=os.getenv("JARVIS_TTS_BACKEND", tts_raw.get("backend", "pyttsx3")).lower(),
        voice=os.getenv("JARVIS_TTS_VOICE", tts_raw.get("voice", "")),
        rate=int(os.getenv("JARVIS_TTS_RATE", tts_raw.get("rate", 185))),
        volume=float(os.getenv("JARVIS_TTS_VOLUME", tts_raw.get("volume", 1.0))),
        edge_rate=os.getenv("JARVIS_TTS_EDGE_RATE", tts_raw.get("edge_rate", "+0%")),
        edge_volume=os.getenv("JARVIS_TTS_EDGE_VOLUME", tts_raw.get("edge_volume", "+0%")),
    )

    visual = VisualSettings(
        enabled=_env_bool("JARVIS_VISUAL_OUTPUT", visual_raw.get("enabled", True)),
        always_on_top=_env_bool(
            "JARVIS_VISUAL_ALWAYS_ON_TOP",
            visual_raw.get("always_on_top", True),
        ),
        width=int(os.getenv("JARVIS_VISUAL_WIDTH", visual_raw.get("width", 520))),
        height=int(os.getenv("JARVIS_VISUAL_HEIGHT", visual_raw.get("height", 320))),
        duration_seconds=float(
            os.getenv("JARVIS_VISUAL_DURATION_SECONDS", visual_raw.get("duration_seconds", 45))
        ),
        show_startup=_env_bool(
            "JARVIS_VISUAL_SHOW_STARTUP",
            visual_raw.get("show_startup", False),
        ),
        show_wake=_env_bool("JARVIS_VISUAL_SHOW_WAKE", visual_raw.get("show_wake", False)),
        show_heard=_env_bool("JARVIS_VISUAL_SHOW_HEARD", visual_raw.get("show_heard", False)),
        show_final=_env_bool("JARVIS_VISUAL_SHOW_FINAL", visual_raw.get("show_final", True)),
    )

    security = SecuritySettings(
        allowed_paths=allowed_paths,
        command_timeout_seconds=int(security_raw.get("command_timeout_seconds", 60)),
        file_read_limit_bytes=int(security_raw.get("file_read_limit_bytes", 200_000)),
        require_confirmation_for_shell=bool(
            security_raw.get("require_confirmation_for_shell", False)
        ),
    )

    memory = MemorySettings(db_path=data_dir / "memory.sqlite3")

    return Settings(
        base_dir=base_dir,
        data_dir=data_dir,
        assistant=assistant,
        llm=llm,
        audio=audio,
        tts=tts,
        visual=visual,
        security=security,
        memory=memory,
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if yaml is None:
        raise RuntimeError("PyYAML is required to read config.yaml. Run pip install -r requirements.txt.")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {path}")
    return data


def _resolve_allowed_paths(base_dir: Path, configured: list[str], env_value: str) -> list[Path]:
    values: list[str] = []
    values.extend(str(item) for item in configured if item)
    if env_value:
        values.extend(item for item in env_value.split(";") if item.strip())

    roots = [base_dir, Path.home()]
    for value in values:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = base_dir / candidate
        roots.append(candidate)

    resolved: list[Path] = []
    for root in roots:
        item = root.resolve()
        if item not in resolved:
            resolved.append(item)
    return resolved


def _env_bool(name: str, default: Any) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes", "on"}
