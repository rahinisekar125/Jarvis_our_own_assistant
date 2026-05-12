from __future__ import annotations

import json
import logging
import subprocess
import sys
import uuid
from pathlib import Path

from ..config import VisualSettings

LOGGER = logging.getLogger(__name__)


class VisualOutput:
    def show(self, title: str, message: str, variant: str = "output") -> str:
        raise NotImplementedError

    def close(self) -> None:
        return None

    def is_cancelled(self, session_id: str) -> bool:
        return False

    def is_open(self, session_id: str) -> bool:
        return False


class NullVisualOutput(VisualOutput):
    def show(self, title: str, message: str, variant: str = "output") -> str:
        return ""


class PopupVisualOutput(VisualOutput):
    def __init__(self, settings: VisualSettings, data_dir: Path) -> None:
        self.settings = settings
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.payload_path = self.data_dir / "visual_output.json"
        self.cancel_path = self.data_dir / "visual_cancel.json"
        self._process: subprocess.Popen | None = None
        self._session_id = ""

    def show(self, title: str, message: str, variant: str = "output") -> str:
        session_id = uuid.uuid4().hex
        payload = {
            "session_id": session_id,
            "title": title,
            "message": message,
            "variant": variant,
            "cancel_path": str(self.cancel_path),
            "always_on_top": self.settings.always_on_top,
            "width": self.settings.width,
            "height": self.settings.height,
            "duration_seconds": self.settings.duration_seconds,
        }
        self._session_id = session_id
        self._clear_cancel_signal()
        self.payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self._stop_previous()
        try:
            self._process = subprocess.Popen(
                [sys.executable, "-m", "jarvis_assistant.ui.popup_window", str(self.payload_path)],
                cwd=Path.cwd(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
        except Exception as exc:  # noqa: BLE001 - visual output must not break voice mode.
            LOGGER.warning("Could not launch visual popup: %s", exc)
        return session_id

    def close(self) -> None:
        self._stop_previous()

    def is_cancelled(self, session_id: str) -> bool:
        if not session_id or not self.cancel_path.exists():
            return False
        try:
            payload = json.loads(self.cancel_path.read_text(encoding="utf-8"))
        except Exception:
            return False
        return str(payload.get("session_id", "")) == session_id

    def is_open(self, session_id: str) -> bool:
        if session_id and session_id != self._session_id:
            return False
        return self._process is not None and self._process.poll() is None

    def _stop_previous(self) -> None:
        if self._process is None:
            return
        if self._process.poll() is None:
            try:
                self._process.terminate()
            except OSError:
                pass
        self._process = None

    def _clear_cancel_signal(self) -> None:
        try:
            self.cancel_path.unlink(missing_ok=True)
        except OSError:
            LOGGER.debug("Could not clear visual cancel signal: %s", self.cancel_path)


def create_visual_output(settings: VisualSettings, data_dir: Path) -> VisualOutput:
    if not settings.enabled:
        return NullVisualOutput()
    try:
        return PopupVisualOutput(settings, data_dir)
    except Exception as exc:  # noqa: BLE001 - voice mode should keep running.
        LOGGER.warning("Could not start visual output: %s", exc)
        return NullVisualOutput()
