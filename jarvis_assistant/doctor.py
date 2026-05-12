from __future__ import annotations

import importlib.util
import platform
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import Settings


@dataclass(slots=True)
class Check:
    name: str
    ok: bool
    detail: str
    warning: bool = False


def run_doctor(settings: Settings, strict: bool = False) -> int:
    checks = build_checks(settings)
    for check in checks:
        status = "OK" if check.ok else "WARN" if check.warning else "FAIL"
        print(f"[{status}] {check.name}: {check.detail}")

    failures = [check for check in checks if not check.ok and not check.warning]
    warnings = [check for check in checks if not check.ok and check.warning]
    if failures or (strict and warnings):
        print()
        print(f"Doctor found {len(failures)} failure(s) and {len(warnings)} warning(s).")
        return 1

    print()
    print(f"Doctor passed with {len(warnings)} warning(s).")
    return 0


def build_checks(settings: Settings) -> list[Check]:
    checks: list[Check] = []
    checks.append(_python_version_check())
    checks.append(_windows_check())
    checks.append(_env_file_check(settings.base_dir))
    checks.append(_data_dir_check(settings.data_dir))
    checks.extend(_dependency_checks(settings))
    checks.extend(_llm_checks(settings))
    checks.extend(_voice_asset_checks(settings))
    checks.append(_demo_video_check(settings.base_dir))
    return checks


def _python_version_check() -> Check:
    version = ".".join(str(part) for part in sys.version_info[:3])
    ok = sys.version_info >= (3, 11)
    return Check("Python", ok, f"{version}; Python 3.11+ is required")


def _windows_check() -> Check:
    system = platform.system()
    return Check("Operating system", system == "Windows", f"{system}; Windows is required for full desktop automation", warning=True)


def _env_file_check(base_dir: Path) -> Check:
    env_path = base_dir / ".env"
    return Check(".env file", env_path.exists(), f"{env_path} {'exists' if env_path.exists() else 'is missing'}", warning=True)


def _data_dir_check(data_dir: Path) -> Check:
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="jarvis-doctor-", dir=data_dir, delete=True):
            pass
        return Check("Data directory", True, f"{data_dir} is writable")
    except OSError as exc:
        return Check("Data directory", False, f"{data_dir} is not writable: {exc}")


def _dependency_checks(settings: Settings) -> list[Check]:
    packages = {
        "bs4": "beautifulsoup4",
        "dotenv": "python-dotenv",
        "psutil": "psutil",
        "requests": "requests",
        "sounddevice": "sounddevice",
        "yaml": "PyYAML",
    }
    if settings.audio.stt_engine == "whisper" or settings.audio.wake_engine == "whisper":
        packages["faster_whisper"] = "faster-whisper"
    if settings.audio.stt_engine == "vosk" or settings.audio.wake_engine == "vosk":
        packages["vosk"] = "vosk"
    if settings.tts.backend == "edge":
        packages["edge_tts"] = "edge-tts"
    if settings.tts.backend == "pyttsx3":
        packages["pyttsx3"] = "pyttsx3"

    checks = []
    for module_name, package_name in sorted(packages.items(), key=lambda item: item[1].lower()):
        found = importlib.util.find_spec(module_name) is not None
        checks.append(Check(f"Dependency {package_name}", found, "installed" if found else "missing"))
    return checks


def _llm_checks(settings: Settings) -> list[Check]:
    checks: list[Check] = []
    providers = {settings.llm.provider, settings.llm.voice_provider}
    if "gemini" in providers:
        checks.append(
            Check(
                "Gemini API key",
                bool(settings.llm.gemini_api_key.strip()),
                "configured" if settings.llm.gemini_api_key.strip() else "GEMINI_API_KEY is empty; local fallback can still run",
                warning=True,
            )
        )
    if "ollama" in providers or settings.llm.ollama_backup_enabled or settings.llm.voice_ollama_backup_enabled:
        checks.append(_ollama_check(settings.llm.ollama_base_url))
    return checks


def _ollama_check(base_url: str) -> Check:
    try:
        import requests

        response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=1)
        ok = response.status_code == 200
        return Check("Ollama", ok, f"{base_url} returned HTTP {response.status_code}", warning=True)
    except Exception as exc:  # noqa: BLE001 - endpoint availability is a deployment hint.
        return Check("Ollama", False, f"{base_url} is not reachable: {exc.__class__.__name__}", warning=True)


def _voice_asset_checks(settings: Settings) -> list[Check]:
    checks: list[Check] = []
    if settings.audio.stt_engine == "vosk" or settings.audio.wake_engine == "vosk":
        model_path = Path(settings.audio.wake_vosk_model_path)
        if not model_path.is_absolute():
            model_path = settings.base_dir / model_path
        checks.append(
            Check(
                "Vosk model",
                model_path.exists(),
                f"{model_path} {'exists' if model_path.exists() else 'is missing; run scripts/install_windows.ps1'}",
            )
        )
    return checks


def _demo_video_check(base_dir: Path) -> Check:
    demo = base_dir / "outputs" / "jarvis_working_demo" / "Jarvis_Working_Demo.mp4"
    if not demo.exists():
        return Check("Demo video", False, f"{demo} is missing", warning=True)
    size_mb = demo.stat().st_size / (1024 * 1024)
    return Check("Demo video", size_mb > 0.1, f"{demo} ({size_mb:.1f} MB)", warning=True)
