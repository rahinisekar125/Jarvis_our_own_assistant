from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import threading
import time
from copy import copy
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from .agent.agent import JarvisAgent
from .agent.llm_manager import create_llm_client
from .agent.memory import MemoryStore
from .audio.tts import create_async_speaker, create_speaker
from .config import Settings, load_settings
from .doctor import run_doctor
from .executor.executor import ConsoleConfirmationProvider, ToolExecutor
from .executor.safety import SafetyPolicy
from .logging_config import configure_logging
from .tools.defaults import build_default_registry
from .ui.output_window import create_visual_output

LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass(slots=True)
class Runtime:
    settings: Settings
    agent: JarvisAgent


class AsyncResource(Generic[T]):
    def __init__(self, name: str, factory: Callable[[], T]) -> None:
        self.name = name
        self._factory = factory
        self._ready = threading.Event()
        self._value: T | None = None
        self._error: BaseException | None = None
        self._thread = threading.Thread(target=self._load, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def get(self) -> T:
        self._ready.wait()
        if self._error is not None:
            raise RuntimeError(f"{self.name} failed to initialize") from self._error
        if self._value is None:
            raise RuntimeError(f"{self.name} did not initialize")
        return self._value

    def _load(self) -> None:
        try:
            self._value = self._factory()
            LOGGER.info("%s initialized", self.name)
        except BaseException as exc:  # noqa: BLE001 - surfaced when resource is used.
            self._error = exc
            LOGGER.exception("%s initialization failed", self.name)
        finally:
            self._ready.set()


def build_runtime(settings: Settings, enable_voice_prompts: bool = False) -> Runtime:
    speaker = create_speaker(settings.tts) if enable_voice_prompts else None
    memory = MemoryStore(settings.memory.db_path)
    registry = build_default_registry(settings)
    safety = SafetyPolicy(settings.security)
    confirmer = ConsoleConfirmationProvider(speaker=speaker)
    executor = ToolExecutor(registry=registry, safety=safety, confirmer=confirmer, memory=memory)
    llm = create_llm_client(settings.llm)
    agent = JarvisAgent(
        llm=llm,
        registry=registry,
        executor=executor,
        memory=memory,
        assistant_settings=settings.assistant,
    )
    return Runtime(settings=settings, agent=agent)


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(description="Local Jarvis-style assistant")
    parser.add_argument("--mode", choices=["cli", "voice", "voice-supervisor", "server"], default="cli")
    parser.add_argument("--config", default=None)
    parser.add_argument("--text", default=None, help="Run one text command and exit")
    parser.add_argument("--list-tools", action="store_true")
    parser.add_argument("--doctor", action="store_true", help="Check deployment readiness and exit")
    parser.add_argument("--strict", action="store_true", help="Treat doctor warnings as failures")
    parser.add_argument("--no-wake", action="store_true", help="Voice mode starts recording immediately")
    parser.add_argument("--host", default="127.0.0.1", help="Host for --mode server")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8765")), help="Port for --mode server")
    parser.add_argument("--public", action="store_true", help="Run --mode server with public-safe command handling")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    settings = load_settings(args.config)
    if args.mode in {"voice", "voice-supervisor"}:
        settings.llm = _voice_optimized_llm_settings(settings.llm)
    configure_logging(settings.data_dir, verbose=args.verbose)

    if args.doctor:
        return run_doctor(settings, strict=args.strict)

    if args.mode == "voice-supervisor":
        return run_voice_supervisor(settings)

    if args.mode == "server":
        from .local_server import run_local_server

        return run_local_server(settings, host=args.host, port=args.port, public=args.public)

    runtime = build_runtime(settings, enable_voice_prompts=False)

    if args.list_tools:
        for tool in runtime.agent.registry.list_tools():
            print(f"{tool.name}: {tool.description}")
        return 0

    if args.text:
        result = runtime.agent.process(args.text)
        print(result.response)
        return 0 if result.ok else 1

    if args.mode == "voice":
        return run_voice_loop(runtime, no_wake=args.no_wake)

    return run_cli_loop(runtime)


def run_cli_loop(runtime: Runtime) -> int:
    print("Jarvis CLI ready. Type 'exit' to quit.")
    while True:
        try:
            user_text = input("You> ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return 0

        if user_text.lower() in {"exit", "quit", "bye"}:
            return 0
        if not user_text:
            continue

        result = runtime.agent.process(user_text)
        print(f"Jarvis> {result.response}")


def run_voice_loop(runtime: Runtime, no_wake: bool = False) -> int:
    from .audio.stt import create_transcriber
    from .audio.wake_word import create_wake_word_detector

    speaker = create_async_speaker(runtime.settings.tts)
    visual = create_visual_output(runtime.settings.visual, runtime.settings.data_dir)
    _start_voice_llm_warmup(runtime.settings.llm)
    wake_word = None if no_wake else create_wake_word_detector(
        runtime.settings.audio,
        runtime.settings.data_dir / "tmp",
        allow_keyboard_fallback=False,
    )
    stt_loader = AsyncResource(
        "Speech transcriber",
        lambda: create_transcriber(runtime.settings.audio, runtime.settings.data_dir / "tmp"),
    )
    stt_loader.start()

    if runtime.settings.visual.show_startup:
        visual.show("Jarvis", "Jarvis is online.")
    print("Jarvis voice mode ready. Press Ctrl+C to exit.")

    while True:
        try:
            if wake_word is not None:
                print("Listening for wake word...")
                LOGGER.info("Listening for wake word")
                voice_event = wake_word.wait_for_wake_word()
                if voice_event == "cancel":
                    _cancel_speaker(speaker)
                    visual.close()
                    LOGGER.info("Voice quit command detected; speech stopped")
                    continue
                LOGGER.info("Wake word detected")
            LOGGER.info("Wake greeting: %s", runtime.settings.audio.wake_greeting)
            wake_session = ""
            if runtime.settings.visual.show_wake:
                wake_session = visual.show(
                    "Jarvis",
                    f"{runtime.settings.audio.wake_greeting}\n\nListening...",
                    variant="wake",
                )
            if wake_word is not None:
                _wake_ack()
            if runtime.settings.audio.speak_wake_greeting:
                speaker.speak(runtime.settings.audio.wake_greeting)
                _stop_speech_when_popup_cancelled(visual, speaker, wake_session)
            print("Recording command...")
            stt = stt_loader.get()
            user_text = stt.listen_and_transcribe()
            if _visual_cancelled(visual, wake_session):
                _cancel_speaker(speaker)
                LOGGER.info("Wake popup cancelled; command discarded")
                continue
            if _is_quit_command(user_text):
                _cancel_speaker(speaker)
                visual.close()
                LOGGER.info("Quit command heard; returning to wake listening")
                continue
            if not user_text:
                _show_and_speak(visual, speaker, "Jarvis", "I did not catch that.")
                continue

            print(f"You> {user_text}")
            if runtime.settings.visual.show_heard:
                visual.show("Jarvis heard you", f"You said:\n{user_text}\n\nWorking on it...", variant="heard")
            result = runtime.agent.process(user_text)
            print(f"Jarvis> {result.response}")
            final_session = ""
            if runtime.settings.visual.show_final:
                final_session = visual.show(
                    "Jarvis output",
                    f"You said:\n{user_text}\n\nJarvis:\n{result.response}",
                    variant="final",
                )
            speaker.speak(result.response)
            _stop_speech_when_popup_cancelled(visual, speaker, final_session)
            LOGGER.info("Voice command completed; returning to wake listening")
        except KeyboardInterrupt:
            print()
            _show_and_speak(visual, speaker, "Jarvis", "Shutting down.")
            visual.close()
            close_speaker = getattr(speaker, "close", None)
            if callable(close_speaker):
                close_speaker(wait=False)
            return 0
        except Exception as exc:  # noqa: BLE001 - keep voice loop alive.
            LOGGER.exception("Voice loop error")
            print(f"Voice loop error: {exc}")
            _show_and_speak(visual, speaker, "Jarvis error", "I hit an error, but I am still online.")
            time.sleep(1)


def _show_and_speak(visual, speaker, title: str, message: str) -> None:
    session_id = visual.show(title, message)
    speaker.speak(message)
    _stop_speech_when_popup_cancelled(visual, speaker, session_id)


def _stop_speech_when_popup_cancelled(visual, speaker, session_id: str) -> None:
    if not session_id:
        return

    def monitor() -> None:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if _visual_cancelled(visual, session_id):
                _cancel_speaker(speaker)
                LOGGER.info("Popup cancelled; speech stopped session=%s", session_id)
                return
            if not _visual_open(visual, session_id):
                return
            time.sleep(0.05)

    threading.Thread(target=monitor, daemon=True).start()


def _visual_cancelled(visual, session_id: str) -> bool:
    if not session_id:
        return False
    is_cancelled = getattr(visual, "is_cancelled", None)
    return bool(callable(is_cancelled) and is_cancelled(session_id))


def _visual_open(visual, session_id: str) -> bool:
    if not session_id:
        return False
    is_open = getattr(visual, "is_open", None)
    return bool(callable(is_open) and is_open(session_id))


def _cancel_speaker(speaker) -> None:
    cancel = getattr(speaker, "cancel", None)
    if callable(cancel):
        cancel()


def _is_quit_command(text: str) -> bool:
    return " ".join(text.lower().strip().split()) == "quit"


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001 - stdio safety is best-effort.
                pass


def _wake_ack() -> None:
    if sys.platform != "win32":
        return
    try:
        import winsound

        winsound.Beep(880, 90)
    except Exception:  # noqa: BLE001 - acknowledgement sound is best-effort.
        LOGGER.debug("Wake acknowledgement sound failed", exc_info=True)


def _start_voice_llm_warmup(llm_settings) -> None:
    if llm_settings.provider != "ollama":
        return
    thread = threading.Thread(target=_warm_ollama_model, args=(llm_settings,), daemon=True)
    thread.start()


def _warm_ollama_model(llm_settings) -> None:
    try:
        import requests

        response = requests.post(
            f"{llm_settings.ollama_base_url}/api/generate",
            json={
                "model": llm_settings.ollama_model,
                "prompt": ".",
                "stream": False,
                "keep_alive": "30m",
                "options": {"num_predict": 1},
            },
            timeout=min(10, llm_settings.ollama_timeout_seconds),
        )
        LOGGER.info(
            "Ollama warmup status=%s model=%s",
            response.status_code,
            llm_settings.ollama_model,
        )
    except Exception as exc:  # noqa: BLE001 - warmup is an optimization only.
        LOGGER.warning("Ollama warmup skipped: %s", exc)


def _voice_optimized_llm_settings(llm_settings):
    optimized = copy(llm_settings)
    optimized.provider = llm_settings.voice_provider
    optimized.timeout_seconds = llm_settings.voice_timeout_seconds
    optimized.max_retries = llm_settings.voice_max_retries
    optimized.retry_base_delay_seconds = llm_settings.voice_retry_base_delay_seconds
    optimized.cooldown_seconds = llm_settings.voice_cooldown_seconds
    optimized.ollama_timeout_seconds = llm_settings.voice_timeout_seconds
    optimized.ollama_max_retries = llm_settings.voice_max_retries
    optimized.ollama_backup_enabled = llm_settings.voice_ollama_backup_enabled
    return optimized


def run_voice_supervisor(settings: Settings) -> int:
    lock_handle = _acquire_supervisor_lock(settings)
    if lock_handle is None:
        LOGGER.warning("Jarvis voice supervisor already appears to be running; exiting duplicate instance")
        return 0

    LOGGER.info("Jarvis voice supervisor started")
    command = [sys.executable, "-m", "jarvis_assistant", "--mode", "voice"]

    while True:
        process: subprocess.Popen | None = None
        try:
            process = subprocess.Popen(
                command,
                cwd=settings.base_dir,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            LOGGER.info("Started Jarvis voice worker pid=%s", process.pid)
            exit_code = process.wait()
            LOGGER.warning("Jarvis voice worker exited pid=%s code=%s; restarting", process.pid, exit_code)
            time.sleep(3)
        except KeyboardInterrupt:
            if process is not None and process.poll() is None:
                process.terminate()
            return 0
        except Exception:  # noqa: BLE001 - supervisor must keep the assistant alive.
            LOGGER.exception("Jarvis voice supervisor error; retrying")
            time.sleep(5)


def _acquire_supervisor_lock(settings: Settings):
    lock_path = settings.data_dir / "jarvis_voice_supervisor.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = lock_path.open("a+b")
    try:
        import msvcrt

        if lock_file.tell() == 0 and lock_path.stat().st_size == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        return lock_file
    except Exception:  # noqa: BLE001 - duplicate/unsupported lock path means do not start.
        lock_file.close()
        return None
