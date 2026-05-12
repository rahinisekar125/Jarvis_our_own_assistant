from __future__ import annotations

import argparse
import asyncio
import math
import re
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "outputs" / "jarvis_explainer"
FRAME_DIR = OUT_DIR / "frames"
AUDIO_DIR = OUT_DIR / "audio"
SEGMENT_DIR = OUT_DIR / "segments"
FINAL_VIDEO = OUT_DIR / "Jarvis_Functionality_Explainer.mp4"
SCRIPT_PATH = OUT_DIR / "Jarvis_Functionality_Explainer_Script.txt"
PREVIEW_PATH = OUT_DIR / "Jarvis_Functionality_Explainer_Preview.png"

SIZE = (1920, 1080)
FPS = 24
DEFAULT_VOICE = "en-IN-PrabhatNeural"


@dataclass(frozen=True)
class Slide:
    title: str
    subtitle: str
    bullets: tuple[str, ...]
    narration: str
    kind: str


SLIDES = [
    Slide(
        title="Jarvis",
        subtitle="Local AI voice assistant for Ayush's Windows laptop",
        bullets=(
            "Only wake command: Hey Jarvis",
            "Fullscreen cyber listening popup",
            "Fast Indian English and Hinglish command recognition",
            "Speaks, shows results, and returns to standby",
        ),
        narration=(
            "This video shows the current Jarvis system running locally on Ayush's Windows laptop. "
            "Jarvis wakes only on Hey Jarvis, opens a fullscreen tech console, listens for a command, "
            "runs safe local actions, shows the result, speaks back, and then returns to standby."
        ),
        kind="hero",
    ),
    Slide(
        title="Wake Flow",
        subtitle="The only activation phrase is Hey Jarvis",
        bullets=(
            "Vosk listens offline for exactly Hey Jarvis",
            "No cloud request is needed for wake detection",
            "The fullscreen listening UI appears immediately",
            "Closing the popup cancels the active command cycle",
        ),
        narration=(
            "The wake layer is local and fast. It listens for exactly Hey Jarvis. "
            "When detected, Jarvis opens the fullscreen cyber listening screen and begins command mode. "
            "If the popup is cancelled, Jarvis stops that cycle and goes back to listening for the wake word."
        ),
        kind="wake",
    ),
    Slide(
        title="Responsive Speech",
        subtitle="Optimized for Indian English and Hinglish commands",
        bullets=(
            "Whisper runs with English plus Hinglish hotwords",
            "Common words include kholo, batao, chalao, likho, and dhoondo",
            "Silence stop is tuned to 0.32 seconds",
            "The command model warms in the background",
        ),
        narration=(
            "Command recognition is tuned for Indian English and Hinglish. "
            "Whisper uses hotwords like kholo, batao, chalao, likho, dhoondo, Chrome, YouTube, battery, and time. "
            "Short silence detection and model warmup make the assistant feel much more responsive."
        ),
        kind="speech",
    ),
    Slide(
        title="Command Examples",
        subtitle="Natural actions from voice",
        bullets=(
            "Hey Jarvis, time batao",
            "Hey Jarvis, battery status batao",
            "Hey Jarvis, open Notepad and type abc",
            "Hey Jarvis, YouTube par Arijit Singh chalao",
        ),
        narration=(
            "Jarvis understands practical voice commands. You can ask for the time, battery status, "
            "open applications, type text into apps, search the web, or play media. "
            "Notepad is only one example; the same open and type flow can be used with other supported applications."
        ),
        kind="commands",
    ),
    Slide(
        title="Agent Brain",
        subtitle="Gemini first, Ollama backup, local fast intents",
        bullets=(
            "Fast local intents skip slow model calls",
            "Gemini handles richer reasoning",
            "Ollama llama3.2:1b is available as backup",
            "Tool choices are structured as JSON decisions",
        ),
        narration=(
            "The brain is layered for speed and reliability. Common commands stay local and do not call the cloud. "
            "For richer tasks, Gemini plans the action with structured JSON. "
            "If the primary brain is unstable, Jarvis can switch to the local Ollama backup."
        ),
        kind="brain",
    ),
    Slide(
        title="Tool System",
        subtitle="Actions Jarvis can choose dynamically",
        bullets=(
            "Open apps, websites, files, and folders",
            "Run validated shell commands",
            "Read and write allowed project files",
            "Search the web and control the browser",
            "Handle git, Docker, deployments, and tasks",
        ),
        narration=(
            "Jarvis has a modular tool system. It can open desktop apps, control browser pages, "
            "search the web, read or write files, check system information, and help with developer workflows "
            "such as git, Docker, deployments, and task boards."
        ),
        kind="tools",
    ),
    Slide(
        title="Safety Layer",
        subtitle="Real local power with guardrails",
        bullets=(
            "Dangerous shell patterns are blocked",
            "Critical actions can require confirmation",
            "File access is constrained to allowed paths",
            "Errors are logged without killing the listener",
        ),
        narration=(
            "Because Jarvis can perform real operating system actions, it includes a safety layer. "
            "High-risk commands are blocked or confirmed, file operations stay inside allowed areas, "
            "and errors are handled so the voice loop keeps running."
        ),
        kind="safety",
    ),
    Slide(
        title="Memory and Feedback",
        subtitle="Context for better follow-up behavior",
        bullets=(
            "SQLite stores recent commands and responses",
            "Preferences and notes can be remembered",
            "Tool results are returned to the agent",
            "Detailed logs track model, retries, and execution",
        ),
        narration=(
            "Jarvis stores memory in SQLite. It keeps recent commands, assistant responses, preferences, "
            "and useful context. After a tool runs, the result is logged and can be used by the agent "
            "to refine the response."
        ),
        kind="memory",
    ),
    Slide(
        title="Fullscreen Output",
        subtitle="Cyber console results with speech control",
        bullets=(
            "Final answers open in a fullscreen tech popup",
            "The popup has Copy and Quit Speaking controls",
            "Press Q or Escape to stop speech",
            "Saying quit stops speech and returns to standby",
        ),
        narration=(
            "The visual output is now fullscreen and matches the Jarvis cyber interface. "
            "When Jarvis answers, the result appears on screen and is spoken aloud. "
            "You can press Q, press Escape, close the popup, or say quit to stop speaking and return to standby."
        ),
        kind="visual",
    ),
    Slide(
        title="Developer Mode",
        subtitle="Useful for daily project work",
        bullets=(
            "Open today's tasks",
            "Check git status",
            "List or run Docker containers",
            "Run deployment workflows when configured",
            "Show files and current working directory",
        ),
        narration=(
            "Developer mode helps with daily work. Jarvis can open today's tasks, check git status, "
            "list Docker containers, start Docker Compose, show files, show the current directory, "
            "and run deployment workflows when the project provides them."
        ),
        kind="dev",
    ),
    Slide(
        title="Ready to Use",
        subtitle="Wake, command, action, output, standby",
        bullets=(
            "Say Hey Jarvis",
            "Watch the fullscreen listening screen",
            "Speak the command naturally",
            "See and hear the result",
            "Say quit anytime to stop speaking",
        ),
        narration=(
            "The final flow is simple. Say Hey Jarvis, wait for the fullscreen listening interface, "
            "speak naturally, and Jarvis will act, show the result, speak the response, and return to standby. "
            "Anytime the speech is too long, say quit and Jarvis stops immediately."
        ),
        kind="ready",
    ),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the Jarvis functionality explainer video.")
    parser.add_argument("--clean", action="store_true", help="Delete previous generated video assets first.")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="Edge TTS voice for draft narration.")
    parser.add_argument("--voice-reference", default="", help="Optional demo audio for a future voice-clone pass.")
    args = parser.parse_args()

    if args.clean and OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FRAME_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SEGMENT_DIR.mkdir(parents=True, exist_ok=True)

    if args.voice_reference:
        reference = Path(args.voice_reference).expanduser()
        if not reference.exists():
            raise FileNotFoundError(f"Voice reference audio not found: {reference}")
        (OUT_DIR / "voice_reference_used.txt").write_text(str(reference.resolve()), encoding="utf-8")

    SCRIPT_PATH.write_text(
        "\n\n".join(f"{i + 1}. {slide.title}\n{slide.narration}" for i, slide in enumerate(SLIDES)),
        encoding="utf-8",
    )

    frame_paths = [render_slide(slide, index) for index, slide in enumerate(SLIDES)]
    shutil.copy2(frame_paths[0], PREVIEW_PATH)
    audio_paths = asyncio.run(render_all_audio(args.voice))
    render_video(frame_paths, audio_paths)
    print(FINAL_VIDEO)


async def render_all_audio(voice: str) -> list[Path]:
    paths: list[Path] = []
    for index, slide in enumerate(SLIDES):
        path = AUDIO_DIR / f"{index + 1:02d}_{slug(slide.title)}.mp3"
        if path.exists():
            path.unlink()
        try:
            import edge_tts

            communicate = edge_tts.Communicate(slide.narration, voice, rate="+8%", volume="+0%")
            await communicate.save(str(path))
        except Exception:
            path = AUDIO_DIR / f"{index + 1:02d}_{slug(slide.title)}.wav"
            render_silence(path, seconds=max(4.5, len(slide.narration) / 120))
        paths.append(path)
    return paths


def render_silence(path: Path, seconds: float) -> None:
    sample_rate = 44100
    total = int(sample_rate * seconds)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(np.zeros(total, dtype=np.int16).tobytes())


def render_video(frame_paths: list[Path], audio_paths: list[Path]) -> None:
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    segment_paths: list[Path] = []

    for index, (frame_path, audio_path) in enumerate(zip(frame_paths, audio_paths, strict=True), start=1):
        segment_path = SEGMENT_DIR / f"{index:02d}_{slug(frame_path.stem)}.mp4"
        segment_paths.append(segment_path)
        run(
            [
                ffmpeg,
                "-y",
                "-loop",
                "1",
                "-framerate",
                str(FPS),
                "-i",
                str(frame_path),
                "-i",
                str(audio_path),
                "-vf",
                "scale=1920:1080:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-tune",
                "stillimage",
                "-crf",
                "19",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-shortest",
                "-movflags",
                "+faststart",
                str(segment_path),
            ]
        )

    concat_path = OUT_DIR / "segments.txt"
    concat_path.write_text(
        "\n".join(f"file '{as_ffmpeg_path(path)}'" for path in segment_paths),
        encoding="utf-8",
    )

    if FINAL_VIDEO.exists():
        FINAL_VIDEO.unlink()
    run(
        [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(FINAL_VIDEO),
        ]
    )


def run(command: list[str]) -> None:
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "Command failed:\n"
            + " ".join(command)
            + "\nSTDOUT:\n"
            + completed.stdout[-4000:]
            + "\nSTDERR:\n"
            + completed.stderr[-4000:]
        )


def as_ffmpeg_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "'\\''")


def render_slide(slide: Slide, index: int) -> Path:
    image = make_background(index)
    draw = ImageDraw.Draw(image, "RGBA")
    fonts = fonts_for_slide()

    draw_matrix(draw, index)
    draw_header(draw, slide, index, fonts)
    draw_bullets(draw, slide, fonts)
    draw_console(draw, slide, index, fonts)
    draw_footer(draw, index, fonts)

    image = image.filter(ImageFilter.UnsharpMask(radius=1, percent=110, threshold=3))
    path = FRAME_DIR / f"{index + 1:02d}_{slug(slide.title)}.png"
    image.save(path, "PNG")
    return path


def make_background(index: int) -> Image.Image:
    width, height = SIZE
    top = np.array((2, 8, 6), dtype=np.float32)
    bottom_options = [
        np.array((4, 28, 22), dtype=np.float32),
        np.array((13, 18, 35), dtype=np.float32),
        np.array((23, 12, 15), dtype=np.float32),
        np.array((9, 26, 35), dtype=np.float32),
    ]
    bottom = bottom_options[index % len(bottom_options)]
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(height):
        t = y / max(1, height - 1)
        row = top * (1 - t) + bottom * t
        arr[y, :, :] = row.astype(np.uint8)
    image = Image.fromarray(arr, "RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rectangle((0, 0, width, height), fill=(0, 0, 0, 58))
    for radius, alpha, cx, cy in (
        (620, 28, 1650, 160),
        (360, 28, 300, 850),
        (240, 38, 1460, 820),
    ):
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(25, 255, 196, alpha))
    return image


def draw_matrix(draw: ImageDraw.ImageDraw, index: int) -> None:
    rng = np.random.default_rng(seed=9000 + index)
    font_obj = font("consola.ttf", 20)
    glyphs = "01JARVISVOICECOREAUDIO"
    for x in range(18, SIZE[0], 34):
        start = int(rng.integers(-220, 80))
        length = int(rng.integers(12, 32))
        for n in range(length):
            y = start + n * 28
            if y < -20 or y > SIZE[1] + 20:
                continue
            alpha = max(18, 190 - n * 7)
            color = (124, 255, 199, alpha) if n < 2 else (12, 165, 116, alpha)
            draw.text((x, y), glyphs[int(rng.integers(0, len(glyphs)))], font=font_obj, fill=color)


def fonts_for_slide() -> dict[str, ImageFont.FreeTypeFont]:
    return {
        "display": font("bahnschrift.ttf", 88),
        "title": font("bahnschrift.ttf", 62),
        "subtitle": font("segoeui.ttf", 31),
        "body": font("segoeui.ttf", 32),
        "body_bold": font("segoeuib.ttf", 34),
        "small": font("segoeui.ttf", 23),
        "mono": font("consola.ttf", 25),
    }


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts") / name,
        Path("C:/Windows/Fonts") / name.upper(),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default(size=size)


def draw_header(draw: ImageDraw.ImageDraw, slide: Slide, index: int, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    draw.rectangle((0, 0, SIZE[0], 112), fill=(1, 12, 10, 214))
    draw.line((0, 112, SIZE[0], 112), fill=(25, 255, 196, 130), width=3)
    draw.text((96, 34), "JARVIS LOCAL SYSTEM", font=fonts["small"], fill=(124, 255, 199, 238))
    draw.text((96, 132), slide.title, font=fonts["display"] if index == 0 else fonts["title"], fill=(246, 255, 252, 255))
    draw.text((102, 226), slide.subtitle, font=fonts["subtitle"], fill=(198, 230, 224, 235))
    draw.rounded_rectangle((1508, 34, 1818, 82), radius=8, outline=(25, 255, 196, 170), width=2, fill=(3, 32, 26, 184))
    draw.text((1532, 44), f"MODULE {index + 1:02d}/{len(SLIDES):02d}", font=fonts["small"], fill=(236, 255, 250, 255))


def draw_bullets(draw: ImageDraw.ImageDraw, slide: Slide, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    x, y, width = 100, 350, 820
    for bullet in slide.bullets:
        draw.rounded_rectangle((x, y, x + width, y + 74), radius=8, fill=(3, 17, 15, 226), outline=(25, 255, 196, 120), width=2)
        draw.rectangle((x, y, x + 9, y + 74), fill=(25, 255, 196, 210))
        draw.text((x + 32, y + 19), bullet, font=fonts["body"], fill=(235, 252, 247, 255))
        y += 91


def draw_console(draw: ImageDraw.ImageDraw, slide: Slide, index: int, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    x0, y0, x1, y1 = 1015, 296, 1818, 870
    draw.rounded_rectangle((x0, y0, x1, y1), radius=10, fill=(2, 13, 11, 232), outline=(25, 255, 196, 185), width=3)
    draw.rectangle((x0, y0, x1, y0 + 64), fill=(3, 34, 28, 236))
    draw.text((x0 + 28, y0 + 18), f"{slide.kind.upper()} CONSOLE", font=fonts["mono"], fill=(124, 255, 199, 255))

    if slide.kind == "commands":
        lines = [
            "> hey jarvis",
            "WAKE CONFIRMED",
            "> notepad kholo aur type abc",
            "ACTION: open_application_and_type",
            "RESULT: text typed successfully",
        ]
        draw_terminal_lines(draw, lines, x0 + 34, y0 + 104, fonts)
    elif slide.kind == "visual":
        draw_fullscreen_mock(draw, x0 + 40, y0 + 105, fonts)
    elif slide.kind == "brain":
        lines = [
            '{ "status": "tool_call",',
            '  "tool": "open_application",',
            '  "arguments": {"app_name": "chrome"}',
            "}",
            "PRIMARY: Gemini | BACKUP: Ollama",
        ]
        draw_terminal_lines(draw, lines, x0 + 34, y0 + 104, fonts)
    elif slide.kind == "tools":
        draw_tool_grid(draw, x0 + 48, y0 + 112, fonts)
    elif slide.kind == "safety":
        draw_shield(draw, (1418, 585), fonts)
    else:
        draw_orb(draw, (1418, 565), 148, index, fonts)
        flow = {
            "hero": ["WAKE", "LISTEN", "THINK", "ACT", "SPEAK"],
            "wake": ["MIC", "VOSK", "HEY JARVIS", "POPUP"],
            "speech": ["VOICE", "WHISPER", "HOTWORDS", "TEXT"],
            "memory": ["COMMAND", "SQLITE", "CONTEXT", "NEXT"],
            "dev": ["GIT", "DOCKER", "TASKS", "DEPLOY"],
            "ready": ["WAKE", "COMMAND", "RESULT", "QUIT"],
        }.get(slide.kind, ["INPUT", "PLAN", "RUN", "OUTPUT"])
        draw_flow(draw, flow, x0 + 58, y1 - 118, fonts)


def draw_terminal_lines(draw: ImageDraw.ImageDraw, lines: list[str], x: int, y: int, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    for index, line in enumerate(lines):
        color = (124, 255, 199, 255) if line.startswith(">") else (248, 215, 109, 255)
        draw.text((x, y + index * 60), line, font=fonts["mono"], fill=color)


def draw_fullscreen_mock(draw: ImageDraw.ImageDraw, x: int, y: int, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    draw.rounded_rectangle((x, y, x + 720, y + 360), radius=8, fill=(1, 8, 7, 255), outline=(25, 255, 196, 160), width=2)
    draw.rectangle((x + 34, y + 38, x + 686, y + 96), fill=(3, 34, 28, 230))
    draw.text((x + 58, y + 53), "OUTPUT CONSOLE", font=fonts["mono"], fill=(124, 255, 199, 255))
    draw.text((x + 58, y + 132), "Jarvis: Opening Notepad and typing abc.", font=fonts["body"], fill=(235, 252, 247, 255))
    draw.rounded_rectangle((x + 470, y + 286, x + 660, y + 334), radius=6, fill=(49, 19, 17, 235), outline=(255, 126, 101, 170), width=2)
    draw.text((x + 498, y + 298), "Quit Speaking", font=fonts["small"], fill=(255, 215, 202, 255))


def draw_tool_grid(draw: ImageDraw.ImageDraw, x: int, y: int, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    tools = ["SHELL", "APPS", "FILES", "WEB", "BROWSER", "SYSTEM", "GIT", "DOCKER"]
    for i, label in enumerate(tools):
        col, row = i % 2, i // 2
        xx, yy = x + col * 340, y + row * 90
        draw.rounded_rectangle((xx, yy, xx + 286, yy + 58), radius=8, fill=(3, 34, 28, 224), outline=(25, 255, 196, 150), width=2)
        draw.text((xx + 22, yy + 15), label, font=fonts["small"], fill=(238, 255, 250, 255))


def draw_shield(draw: ImageDraw.ImageDraw, center: tuple[int, int], fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    cx, cy = center
    points = [(cx, cy - 170), (cx + 160, cy - 90), (cx + 116, cy + 125), (cx, cy + 212), (cx - 116, cy + 125), (cx - 160, cy - 90)]
    draw.polygon(points, fill=(255, 112, 104, 52), outline=(255, 112, 104, 230))
    draw.line((cx - 72, cy + 8, cx - 20, cy + 62, cx + 88, cy - 78), fill=(245, 255, 252, 250), width=13)
    draw_centered(draw, "SAFE EXECUTION", (cx, cy + 270), fonts["body_bold"], (245, 255, 252, 255))


def draw_orb(draw: ImageDraw.ImageDraw, center: tuple[int, int], radius: int, index: int, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    cx, cy = center
    for i in range(7):
        r = radius + i * 24
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(25, 255, 196, max(22, 115 - i * 13)), width=3)
    for angle in range(0, 360, 45):
        rad = math.radians(angle + index * 11)
        x = cx + math.cos(rad) * (radius + 78)
        y = cy + math.sin(rad) * (radius + 78)
        draw.line((cx, cy, x, y), fill=(25, 255, 196, 40), width=2)
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(25, 255, 196, 42), outline=(25, 255, 196, 235), width=4)
    draw_centered(draw, "JARVIS", center, fonts["title"], (246, 255, 252, 255))


def draw_flow(draw: ImageDraw.ImageDraw, labels: list[str], x: int, y: int, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    item_w, item_h, gap = 128, 62, 22
    for i, label in enumerate(labels):
        xx = x + i * (item_w + gap)
        draw.rounded_rectangle((xx, y, xx + item_w, y + item_h), radius=8, fill=(3, 34, 28, 224), outline=(25, 255, 196, 160), width=2)
        draw_centered(draw, label, (xx + item_w // 2, y + item_h // 2), fonts["small"], (246, 255, 252, 255))
        if i < len(labels) - 1:
            ax = xx + item_w + 6
            ay = y + item_h // 2
            draw.line((ax, ay, ax + gap - 10, ay), fill=(25, 255, 196, 180), width=3)


def draw_footer(draw: ImageDraw.ImageDraw, index: int, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    draw.line((96, 948, 1824, 948), fill=(25, 255, 196, 90), width=2)
    draw.text((96, 980), "C:/Users/AyushRathour/Documents/New project", font=fonts["mono"], fill=(168, 225, 214, 235))
    draw.text((1628, 980), f"{index + 1:02d} / {len(SLIDES):02d}", font=fonts["mono"], fill=(168, 225, 214, 235))


def draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    center: tuple[int, int],
    font_obj: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
) -> None:
    box = draw.textbbox((0, 0), text, font=font_obj)
    w = box[2] - box[0]
    h = box[3] - box[1]
    draw.text((center[0] - w / 2, center[1] - h / 2 - box[1] / 2), text, font=font_obj, fill=fill)


def slug(text: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip()).strip("_")
    return clean.lower() or "slide"


if __name__ == "__main__":
    main()
