from __future__ import annotations

import json
import random
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        return 1

    payload = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    _show_popup(payload)
    return 0


def _show_popup(payload: dict) -> None:
    variant = str(payload.get("variant", "output")).lower()
    if variant == "wake":
        _show_wake_popup(payload)
        return
    _show_output_popup(payload)


def _show_output_popup(payload: dict) -> None:
    import tkinter as tk

    title = str(payload.get("title", "Jarvis"))
    message = str(payload.get("message", ""))
    always_on_top = bool(payload.get("always_on_top", True))
    duration_seconds = float(payload.get("duration_seconds", 45))

    root = tk.Tk()
    root.title(title)
    root.configure(bg="#020806")
    root.attributes("-topmost", always_on_top)
    root.attributes("-fullscreen", True)

    width = root.winfo_screenwidth()
    height = root.winfo_screenheight()
    canvas = tk.Canvas(root, width=width, height=height, bg="#020806", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    def copy_message() -> None:
        root.clipboard_clear()
        root.clipboard_append(message)

    def request_cancel() -> None:
        _write_cancel_signal(payload)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", request_cancel)
    root.bind("<Escape>", lambda _event: request_cancel())
    root.bind("q", lambda _event: request_cancel())

    panel = tk.Frame(
        root,
        bg="#03110f",
        highlightbackground="#18d9a7",
        highlightcolor="#18d9a7",
        highlightthickness=2,
        padx=22,
        pady=18,
    )
    panel_width = max(720, int(width * 0.84))
    panel_height = max(460, int(height * 0.72))
    panel_window = canvas.create_window(
        width // 2,
        height // 2,
        window=panel,
        width=panel_width,
        height=panel_height,
    )

    header = tk.Frame(panel, bg="#03110f")
    header.pack(fill="x")
    tk.Label(
        header,
        text=title.upper(),
        bg="#03110f",
        fg="#f3fff9",
        font=("Segoe UI", 22, "bold"),
    ).pack(side="left")
    tk.Label(
        header,
        text="OUTPUT CONSOLE",
        bg="#03110f",
        fg="#19ffc4",
        font=("Consolas", 12, "bold"),
    ).pack(side="right")

    status = tk.Label(
        panel,
        text="VOICE RESPONSE ACTIVE  |  LOCAL DISPLAY LINK  |  PRESS Q OR ESC TO QUIT SPEAKING",
        bg="#03110f",
        fg="#6fffd7",
        font=("Consolas", 10),
        anchor="w",
    )
    status.pack(fill="x", pady=(10, 14))

    text = tk.Text(
        panel,
        wrap="word",
        bg="#071412",
        fg="#eafff8",
        insertbackground="#eafff8",
        selectbackground="#0b6b54",
        relief="flat",
        padx=18,
        pady=16,
        font=("Segoe UI", 15),
    )
    text.pack(fill="both", expand=True)
    text.insert("1.0", message)
    text.configure(state="disabled")

    buttons = tk.Frame(panel, bg="#03110f")
    buttons.pack(fill="x", pady=(16, 0))
    tk.Button(
        buttons,
        text="Copy",
        command=copy_message,
        bg="#071412",
        fg="#a8ffe5",
        activebackground="#0d2a24",
        activeforeground="#ffffff",
        relief="flat",
        bd=0,
        padx=18,
        pady=8,
        font=("Segoe UI", 10, "bold"),
    ).pack(side="left")
    tk.Button(
        buttons,
        text="Quit Speaking",
        command=request_cancel,
        bg="#311311",
        fg="#ffd7ca",
        activebackground="#5a1f17",
        activeforeground="#ffffff",
        relief="flat",
        bd=0,
        padx=18,
        pady=8,
        font=("Segoe UI", 10, "bold"),
    ).pack(side="right")

    glyphs = "01JARVIS>_SYSCOREVOICEAUDIO"
    column_width = 18
    columns = [
        {
            "x": x,
            "y": random.randint(-height, 0),
            "speed": random.randint(6, 16),
            "length": random.randint(10, 24),
        }
        for x in range(0, width + column_width, column_width)
    ]
    frame = {"value": 0}

    def draw() -> None:
        frame["value"] += 1
        tick = frame["value"]
        canvas.delete("dynamic")

        for col in columns:
            col["y"] += col["speed"]
            if col["y"] - col["length"] * 18 > height:
                col["y"] = random.randint(-height, -20)
                col["speed"] = random.randint(6, 16)
                col["length"] = random.randint(10, 24)

            for index in range(col["length"]):
                y = col["y"] - index * 18
                if -20 <= y <= height + 20:
                    color = "#7cffc7" if index == 0 else "#0ca574" if index < 4 else "#064f3b"
                    canvas.create_text(
                        col["x"],
                        y,
                        text=random.choice(glyphs),
                        fill=color,
                        font=("Consolas", 10),
                        tags="dynamic",
                    )

        scan_y = 24 + (tick * 9 % max(1, height - 48))
        canvas.create_line(0, scan_y, width, scan_y, fill="#13f7b1", width=2, tags="dynamic")
        canvas.create_line(0, scan_y + 4, width, scan_y + 4, fill="#0b6b54", width=1, tags="dynamic")
        canvas.tag_raise(panel_window)
        root.after(55, draw)

    draw()

    if duration_seconds > 0:
        root.after(int(duration_seconds * 1000), root.destroy)

    root.mainloop()


def _show_wake_popup(payload: dict) -> None:
    import tkinter as tk

    title = str(payload.get("title", "Jarvis"))
    message = str(payload.get("message", "Listening..."))
    always_on_top = bool(payload.get("always_on_top", True))
    duration_seconds = float(payload.get("duration_seconds", 18))
    greeting = _first_line(message) or "Hi Ayush, tell me what you want."

    root = tk.Tk()
    root.title("Jarvis listening")
    root.resizable(False, False)
    root.configure(bg="#020806")
    root.attributes("-topmost", always_on_top)
    root.attributes("-fullscreen", True)
    width = root.winfo_screenwidth()
    height = root.winfo_screenheight()

    def request_cancel() -> None:
        _write_cancel_signal(payload)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", request_cancel)
    root.bind("<Escape>", lambda _event: request_cancel())
    root.bind("q", lambda _event: request_cancel())

    canvas = tk.Canvas(root, width=width, height=height, bg="#020806", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    hide_button = tk.Button(
        root,
        text="Cancel",
        command=request_cancel,
        bg="#071412",
        fg="#a8ffe5",
        activebackground="#0d2a24",
        activeforeground="#ffffff",
        relief="flat",
        bd=0,
        padx=10,
        pady=4,
        font=("Segoe UI", 9),
    )
    hide_window = canvas.create_window(width - 52, height - 28, window=hide_button)

    glyphs = "01JARVIS>_SYSCOREVOICEAUDIO"
    column_width = 16
    columns = [
        {
            "x": x,
            "y": random.randint(-height, 0),
            "speed": random.randint(5, 14),
            "length": random.randint(8, 18),
        }
        for x in range(0, width + column_width, column_width)
    ]
    frame = {"value": 0}

    def draw() -> None:
        frame["value"] += 1
        tick = frame["value"]
        canvas.delete("dynamic")

        for col in columns:
            col["y"] += col["speed"]
            if col["y"] - col["length"] * 18 > height:
                col["y"] = random.randint(-height, -20)
                col["speed"] = random.randint(5, 14)
                col["length"] = random.randint(8, 18)

            for index in range(col["length"]):
                y = col["y"] - index * 18
                if -20 <= y <= height + 20:
                    color = "#7cffc7" if index == 0 else "#0ca574" if index < 4 else "#064f3b"
                    canvas.create_text(
                        col["x"],
                        y,
                        text=random.choice(glyphs),
                        fill=color,
                        font=("Consolas", 10),
                        tags="dynamic",
                    )

        scan_y = 36 + (tick * 7 % max(1, height - 84))
        canvas.create_line(20, scan_y, width - 20, scan_y, fill="#13f7b1", width=2, tags="dynamic")
        canvas.create_line(20, scan_y + 3, width - 20, scan_y + 3, fill="#0b6b54", width=1, tags="dynamic")

        _draw_panel(canvas, width, height, title, greeting, tick)
        canvas.tag_raise(hide_window)
        root.after(55, draw)

    draw()
    root.lift()

    if duration_seconds > 0:
        root.after(int(duration_seconds * 1000), root.destroy)

    root.mainloop()


def _draw_panel(canvas, width: int, height: int, title: str, greeting: str, tick: int) -> None:
    panel_left = 28
    panel_top = 38
    panel_right = width - 28
    panel_bottom = height - 54
    pulse = tick % 36
    ring_color = "#19ffc4" if pulse < 18 else "#0ab486"

    canvas.create_rectangle(
        panel_left,
        panel_top,
        panel_right,
        panel_bottom,
        fill="#03110f",
        outline="#18d9a7",
        width=2,
        tags="dynamic",
    )
    canvas.create_rectangle(
        panel_left + 8,
        panel_top + 8,
        panel_right - 8,
        panel_bottom - 8,
        outline="#0a6f58",
        width=1,
        tags="dynamic",
    )

    cx = panel_left + 74
    cy = panel_top + 74
    canvas.create_oval(cx - 42, cy - 42, cx + 42, cy + 42, outline="#0a5f50", width=2, tags="dynamic")
    canvas.create_arc(
        cx - 50,
        cy - 50,
        cx + 50,
        cy + 50,
        start=(tick * 9) % 360,
        extent=95,
        outline=ring_color,
        width=4,
        style="arc",
        tags="dynamic",
    )
    canvas.create_text(cx, cy - 8, text="AI", fill="#f8d66d", font=("Segoe UI", 18, "bold"), tags="dynamic")
    canvas.create_text(cx, cy + 16, text="ONLINE", fill="#a8ffe5", font=("Segoe UI", 8, "bold"), tags="dynamic")

    text_left = panel_left + 142
    canvas.create_text(
        text_left,
        panel_top + 40,
        text=title.upper(),
        fill="#f3fff9",
        font=("Segoe UI", 18, "bold"),
        anchor="w",
        tags="dynamic",
    )
    canvas.create_text(
        text_left,
        panel_top + 72,
        text="LISTENING FOR COMMAND",
        fill="#19ffc4",
        font=("Segoe UI", 10, "bold"),
        anchor="w",
        tags="dynamic",
    )
    canvas.create_text(
        text_left,
        panel_top + 108,
        text=_ellipsize(greeting, 48),
        fill="#cbeee5",
        font=("Segoe UI", 11),
        anchor="w",
        tags="dynamic",
    )

    meter_left = text_left
    meter_top = panel_top + 146
    for index in range(18):
        bar_height = 8 + ((tick + index * 3) % 28)
        color = "#19ffc4" if index % 3 else "#f8d66d"
        canvas.create_rectangle(
            meter_left + index * 13,
            meter_top + 32 - bar_height,
            meter_left + index * 13 + 7,
            meter_top + 32,
            fill=color,
            outline="",
            tags="dynamic",
        )

    canvas.create_text(
        panel_left + 18,
        panel_bottom - 22,
        text="VOICE LINK ACTIVE  |  WAKE WORD CONFIRMED  |  LOCAL CONTROL READY",
        fill="#6fffd7",
        font=("Consolas", 9),
        anchor="w",
        tags="dynamic",
    )


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def _ellipsize(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."


def _place_bottom_right(root) -> None:
    root.update_idletasks()
    x = max(0, root.winfo_screenwidth() - root.winfo_width() - 24)
    y = max(0, root.winfo_screenheight() - root.winfo_height() - 72)
    root.geometry(f"{root.winfo_width()}x{root.winfo_height()}+{x}+{y}")
    root.lift()


def _write_cancel_signal(payload: dict) -> None:
    cancel_path = str(payload.get("cancel_path", "")).strip()
    if not cancel_path:
        return
    signal = {
        "session_id": str(payload.get("session_id", "")),
        "variant": str(payload.get("variant", "")),
    }
    try:
        Path(cancel_path).write_text(json.dumps(signal), encoding="utf-8")
    except OSError:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
