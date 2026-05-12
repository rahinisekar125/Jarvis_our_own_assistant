from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path

from ..config import Settings
from .base import ToolResult, ToolSpec


APP_ALIASES = {
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "notepad": "notepad.exe",
    "paint": "mspaint.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "terminal": "wt.exe",
    "explorer": "explorer.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "firefox": "firefox.exe",
    "brave": "brave.exe",
    "code": "code.cmd",
    "vscode": "code.cmd",
    "vs code": "code.cmd",
    "visual studio code": "code.cmd",
    "word": "winword.exe",
    "microsoft word": "winword.exe",
    "excel": "excel.exe",
    "microsoft excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "power point": "powerpnt.exe",
    "microsoft powerpoint": "powerpnt.exe",
    "outlook": "outlook.exe",
    "microsoft outlook": "outlook.exe",
    "onenote": "onenote.exe",
    "one note": "onenote.exe",
    "wordpad": "write.exe",
    "task manager": "taskmgr.exe",
    "settings": "ms-settings:",
    "whatsapp": "whatsapp:",
    "spotify": "spotify:",
}


def build_system_tools(settings: Settings) -> list[ToolSpec]:
    def run_shell_command(command: str, cwd: str | None = None) -> ToolResult:
        working_dir = _resolve_cwd(cwd, settings.base_dir, settings.security.allowed_paths)
        completed = subprocess.run(
            command,
            cwd=working_dir,
            shell=True,
            text=True,
            capture_output=True,
            timeout=settings.security.command_timeout_seconds,
        )
        output = (completed.stdout or "").strip()
        error = (completed.stderr or "").strip()
        content = output if output else error
        if not content:
            content = f"Command exited with code {completed.returncode}."
        return ToolResult(
            tool="run_shell_command",
            ok=completed.returncode == 0,
            content=content[:8000],
            data={"returncode": completed.returncode, "cwd": str(working_dir)},
        )

    def open_application(app_name: str) -> ToolResult:
        key = app_name.strip().lower()
        target = APP_ALIASES.get(key, app_name.strip())
        process, resolved = _launch_application(target)

        return ToolResult(
            tool="open_application",
            ok=True,
            content=f"Opened {app_name}.",
            data={"target": resolved, "pid": process.pid if process else None},
        )

    def open_application_and_type(
        app_name: str,
        text: str,
        delay_seconds: float = 0.8,
    ) -> ToolResult:
        clean_app_name = app_name.strip()
        clean_text = text.strip()
        if not clean_app_name:
            return ToolResult(tool="open_application_and_type", ok=False, content="App name is empty.")
        if not clean_text:
            return ToolResult(tool="open_application_and_type", ok=False, content="Text to type is empty.")
        if len(clean_text) > 5000:
            return ToolResult(
                tool="open_application_and_type",
                ok=False,
                content="Text is too long for direct voice typing. Keep it under 5000 characters.",
            )
        if os.name != "nt":
            return ToolResult(
                tool="open_application_and_type",
                ok=False,
                content="Typing into apps is currently implemented for Windows only.",
            )

        key = clean_app_name.lower()
        target = APP_ALIASES.get(key, clean_app_name)
        process, resolved = _launch_application(target)
        time.sleep(max(0.2, min(float(delay_seconds), 5.0)))

        process_id = process.pid if process else None
        window = _wait_for_window(process_id, clean_app_name, resolved, timeout_seconds=6.0)
        if window:
            _focus_window(window)
        elif process_id is not None and not _activate_application(process_id, clean_app_name, resolved):
            return ToolResult(
                tool="open_application_and_type",
                ok=False,
                content=f"Opened {clean_app_name}, but I could not safely focus its window, so I did not type.",
                data={"app_name": clean_app_name, "target": resolved, "pid": process_id},
            )

        _paste_text_windows(clean_text)
        return ToolResult(
            tool="open_application_and_type",
            ok=True,
            content=f"Opened {clean_app_name} and typed the requested text.",
            data={
                "app_name": clean_app_name,
                "target": resolved,
                "pid": process_id,
                "typed_length": len(clean_text),
                "focused_window": bool(window),
            },
        )

    def get_system_info() -> ToolResult:
        import psutil

        battery = psutil.sensors_battery()
        data = {
            "os": platform.platform(),
            "python": platform.python_version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_percent": psutil.cpu_percent(interval=0.5),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage(str(Path.home().anchor or Path.home())).percent,
            "battery_percent": battery.percent if battery else None,
            "plugged_in": battery.power_plugged if battery else None,
        }
        lines = [
            f"OS: {data['os']}",
            f"CPU: {data['cpu_percent']}%",
            f"Memory: {data['memory_percent']}%",
            f"Disk: {data['disk_percent']}%",
        ]
        if battery:
            lines.append(f"Battery: {battery.percent}% plugged_in={battery.power_plugged}")
        return ToolResult(tool="get_system_info", ok=True, content="\n".join(lines), data=data)

    return [
        ToolSpec(
            name="run_shell_command",
            description="Run a shell command after safety validation. Optional cwd must be allowed.",
            parameters={"command": "string", "cwd": "optional string"},
            handler=run_shell_command,
        ),
        ToolSpec(
            name="open_application",
            description="Open a desktop application by common name or executable.",
            parameters={"app_name": "string"},
            handler=open_application,
        ),
        ToolSpec(
            name="open_application_and_type",
            description=(
                "Open a desktop application, focus its window, and type or paste text into it. "
                "Use for commands like 'open notepad and type abc'."
            ),
            parameters={"app_name": "string", "text": "string", "delay_seconds": "optional number"},
            handler=open_application_and_type,
        ),
        ToolSpec(
            name="get_system_info",
            description="Return OS, CPU, memory, disk, and battery information.",
            parameters={},
            handler=get_system_info,
        ),
    ]


def _resolve_cwd(cwd: str | None, default: Path, allowed_roots: list[Path]) -> Path:
    candidate = Path(cwd).expanduser() if cwd else default
    if not candidate.is_absolute():
        candidate = default / candidate
    resolved = candidate.resolve()
    for root in allowed_roots:
        root = root.resolve()
        if resolved == root or root in resolved.parents:
            return resolved
    raise PermissionError(f"cwd is outside allowed paths: {resolved}")


def _launch_application(target: str) -> tuple[subprocess.Popen | None, str]:
    resolved = shutil.which(target) or target
    if os.name != "nt":
        return subprocess.Popen([resolved], shell=False), resolved

    if _looks_like_windows_uri(resolved):
        os.startfile(resolved)  # type: ignore[attr-defined]
        return None, resolved

    try:
        return subprocess.Popen([resolved], shell=False), resolved
    except (FileNotFoundError, OSError):
        process = subprocess.Popen(["cmd", "/c", "start", "", resolved], shell=False)
        return process, resolved


def _looks_like_windows_uri(target: str) -> bool:
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:$", target))


def _wait_for_window(pid: int | None, app_name: str, target: str, timeout_seconds: float):
    import win32gui
    import win32process

    deadline = time.monotonic() + timeout_seconds
    needles = _window_title_needles(app_name, target)
    fallback_match = None
    while time.monotonic() < deadline:
        pid_matches: list[int] = []
        title_matches: list[int] = []

        def collect(hwnd, _extra):
            nonlocal fallback_match
            if not win32gui.IsWindowVisible(hwnd):
                return
            _thread_id, window_pid = win32process.GetWindowThreadProcessId(hwnd)
            title = win32gui.GetWindowText(hwnd).lower()
            if pid is not None and window_pid == pid:
                pid_matches.append(hwnd)
            elif any(needle in title for needle in needles):
                title_matches.append(hwnd)

        win32gui.EnumWindows(collect, None)
        if pid_matches:
            return pid_matches[0]
        if title_matches and fallback_match is None:
            fallback_match = title_matches[0]
        time.sleep(0.1)
    return fallback_match


def _window_title_needles(app_name: str, target: str) -> list[str]:
    text = f"{app_name} {target}".lower()
    aliases = {
        "winword": ["word", "document"],
        "word": ["word", "document"],
        "excel": ["excel", "book"],
        "powerpnt": ["powerpoint", "presentation"],
        "powerpoint": ["powerpoint", "presentation"],
        "outlook": ["outlook"],
        "onenote": ["onenote", "one note"],
        "chrome": ["chrome"],
        "msedge": ["edge"],
        "edge": ["edge"],
        "firefox": ["firefox"],
        "brave": ["brave"],
        "notepad": ["notepad"],
        "mspaint": ["paint"],
        "paint": ["paint"],
        "code": ["visual studio code", "code"],
        "write": ["wordpad", "write"],
        "spotify": ["spotify"],
        "whatsapp": ["whatsapp"],
    }
    needles = [token for key, values in aliases.items() if key in text for token in values]
    needles.extend(part for part in app_name.lower().split() if len(part) >= 3)
    deduped: list[str] = []
    for needle in needles:
        if needle and needle not in deduped:
            deduped.append(needle)
    return deduped


def _activate_application(pid: int, app_name: str, target: str) -> bool:
    try:
        import win32com.client

        shell = win32com.client.Dispatch("WScript.Shell")
        if shell.AppActivate(pid):
            time.sleep(0.2)
            return True
        for needle in _window_title_needles(app_name, target):
            if shell.AppActivate(needle):
                time.sleep(0.2)
                return True
    except Exception:
        return False
    return False


def _focus_window(hwnd) -> None:
    import win32con
    import win32gui

    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.15)
    except Exception:
        return


def _paste_text_windows(text: str) -> None:
    import win32api
    import win32clipboard
    import win32con

    previous_text: str | None = None
    try:
        win32clipboard.OpenClipboard()
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            previous_text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
    finally:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass

    try:
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(ord("V"), 0, 0, 0)
        win32api.keybd_event(ord("V"), 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.1)
    finally:
        if previous_text is not None:
            try:
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(previous_text, win32con.CF_UNICODETEXT)
            finally:
                try:
                    win32clipboard.CloseClipboard()
                except Exception:
                    pass
