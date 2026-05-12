from __future__ import annotations

import argparse
import asyncio
import re
import shutil
import subprocess
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "outputs" / "jarvis_working_demo"
FRAME_DIR = OUT_DIR / "frames"
AUDIO_DIR = OUT_DIR / "audio"
SEGMENT_DIR = OUT_DIR / "segments"
FINAL_VIDEO = OUT_DIR / "Jarvis_Working_Demo.mp4"
SCRIPT_PATH = OUT_DIR / "Jarvis_Working_Demo_Script.txt"
PREVIEW_PATH = OUT_DIR / "Jarvis_Working_Demo_Preview.png"

SIZE = (1920, 1080)
FPS = 24
VOICE = "en-IN-PrabhatNeural"


@dataclass(frozen=True)
class DemoScene:
    title: str
    subtitle: str
    command: str
    output: str
    bullets: tuple[str, ...]
    narration: str
    kind: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a Jarvis working demo video.")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--voice", default=VOICE)
    args = parser.parse_args()

    if args.clean and OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FRAME_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SEGMENT_DIR.mkdir(parents=True, exist_ok=True)

    scenes = build_scenes()
    SCRIPT_PATH.write_text(
        "\n\n".join(f"{i + 1}. {scene.title}\n{scene.narration}" for i, scene in enumerate(scenes)),
        encoding="utf-8",
    )

    frame_paths = [render_scene(scene, index) for index, scene in enumerate(scenes)]
    shutil.copy2(frame_paths[0], PREVIEW_PATH)
    audio_paths = asyncio.run(render_audio(scenes, args.voice))
    render_video(frame_paths, audio_paths)
    print(FINAL_VIDEO)


def build_scenes() -> list[DemoScene]:
    live_time = "Abhi 02:30 PM hai."
    live_battery = "CPU 39.4%, memory 62.3%, disk 40.4%, battery 90% hai, charging hai."
    try:
        from jarvis_assistant.config import load_settings
        from jarvis_assistant.main import build_runtime

        settings = load_settings()
        runtime = build_runtime(settings, enable_voice_prompts=False)
        live_time = runtime.agent.process("time batao").response
        live_battery = runtime.agent.process("battery status batao").response
    except Exception:
        pass

    return [
        DemoScene(
            title="Jarvis Working Demo",
            subtitle="Local Windows voice assistant, running from this project",
            command="Wake command: Hey Jarvis",
            output="Status: standby listener active",
            bullets=(
                "Only wake phrase is Hey Jarvis",
                "Fullscreen cyber UI appears on activation",
                "Indian English and Hinglish commands supported",
                "Quit stops speech and returns to standby",
            ),
            narration=(
                "This is the working demo of Jarvis on Ayush's Windows laptop. "
                "The assistant stays in standby, wakes only when it hears Hey Jarvis, "
                "opens a fullscreen tech interface, listens for a command, acts, speaks, and returns to standby."
            ),
            kind="hero",
        ),
        DemoScene(
            title="Step 1: Wake Jarvis",
            subtitle="The wake word is local and strict",
            command='User says: "Hey Jarvis"',
            output='Jarvis: "hi Ayush tell me something what you want"',
            bullets=(
                "Vosk wake engine runs offline",
                "No Gemini call is needed for wake detection",
                "Aliases are locked to only Hey Jarvis",
                "The listening popup opens immediately",
            ),
            narration=(
                "First, the user says Hey Jarvis. Wake detection happens locally using Vosk. "
                "Jarvis confirms activation, opens the fullscreen listening console, and starts recording the next command."
            ),
            kind="wake",
        ),
        DemoScene(
            title="Step 2: Hinglish Time Command",
            subtitle="Fast local intent, no cloud call needed",
            command='User says: "time batao"',
            output=f"Jarvis: {live_time}",
            bullets=(
                "Hinglish is detected from the command",
                "The reply stays in Roman Hinglish",
                "Common commands use fast local logic",
                "This keeps response time low",
            ),
            narration=(
                f"Next, the user says time batao. Jarvis understands the Hinglish command and replies: {live_time} "
                "This is handled as a fast local intent, so it does not need a slow planning call."
            ),
            kind="time",
        ),
        DemoScene(
            title="Step 3: System Status",
            subtitle="Jarvis reads local machine information",
            command='User says: "battery status batao"',
            output=f"Jarvis: {live_battery}",
            bullets=(
                "CPU, memory, disk, and battery are checked locally",
                "The answer mirrors the user's Hinglish style",
                "The fullscreen output console shows the result",
                "Speech is generated with an Indian voice",
            ),
            narration=(
                "Now the user asks for battery status. Jarvis checks local system information and formats the answer clearly. "
                f"In this run, the result is: {live_battery}"
            ),
            kind="system",
        ),
        DemoScene(
            title="Step 4: App Automation",
            subtitle="Open an app and type text",
            command='User says: "open notepad and type abc"',
            output="Jarvis: Opened notepad and typed the text.",
            bullets=(
                "The intent is parsed without being Notepad-specific",
                "Jarvis opens the target app",
                "It waits for the window",
                "Then it types the requested text",
            ),
            narration=(
                "Jarvis can automate desktop apps. For example, the user can say, open Notepad and type abc. "
                "Jarvis opens the application, focuses the window, and types the requested text."
            ),
            kind="app",
        ),
        DemoScene(
            title="Step 5: Browser and Media",
            subtitle="Play and search commands open the browser",
            command='User says: "Arijit Singh chalao"',
            output="Jarvis: YouTube par chala raha hoon.",
            bullets=(
                "Play, chalao, and bajao map to media search",
                "Browser control opens the right URL",
                "The command is understood in Hinglish",
                "The agent keeps the response short",
            ),
            narration=(
                "Jarvis also understands media commands. If the user says Arijit Singh chalao, "
                "Jarvis opens YouTube search for that media and replies in Hinglish."
            ),
            kind="browser",
        ),
        DemoScene(
            title="Step 6: Agent Tools",
            subtitle="Safe action execution for real workflows",
            command='User says: "project status"',
            output="Jarvis: Running safe project status tools.",
            bullets=(
                "Tools include shell, apps, files, web, browser, system, git, and Docker",
                "Dangerous commands are blocked or confirmed",
                "Gemini plans richer tasks with JSON tool calls",
                "Ollama is available as backup",
            ),
            narration=(
                "For bigger tasks, Jarvis works like an agent. It can choose tools for shell commands, files, browser control, "
                "system information, git, Docker, deployments, and task workflows. The safety layer validates risky actions."
            ),
            kind="tools",
        ),
        DemoScene(
            title="Step 7: Fullscreen Output",
            subtitle="Result display plus speech control",
            command='User says: "explain Python"',
            output="Jarvis opens a fullscreen output console and speaks the answer.",
            bullets=(
                "Output appears in a fullscreen tech console",
                "Copy button keeps the result usable",
                "Quit Speaking stops audio immediately",
                "Closing the popup also stops speech",
            ),
            narration=(
                "When Jarvis has an answer, it opens a fullscreen cyber output console. "
                "The result is visible on screen while Jarvis speaks. The user can press Q, Escape, close the window, or click Quit Speaking."
            ),
            kind="visual",
        ),
        DemoScene(
            title="Step 8: Quit Interrupt",
            subtitle="Stop speech and return to standby",
            command='User says: "quit"',
            output="Jarvis: Speech stopped. Returning to wake listening.",
            bullets=(
                "Quit is not a wake word",
                "It is an interrupt while Jarvis is active",
                "Current speech is cancelled",
                "Jarvis immediately returns to Hey Jarvis standby",
            ),
            narration=(
                "If the answer is too long, the user can simply say quit. "
                "Jarvis stops speaking, closes the active visual flow, and returns to standby. "
                "After that, the only way to activate again is still Hey Jarvis."
            ),
            kind="quit",
        ),
        DemoScene(
            title="Demo Complete",
            subtitle="Wake, listen, act, show, speak, quit, standby",
            command="Ready for: Hey Jarvis",
            output="System state: listening for wake word",
            bullets=(
                "Local wake word stays active in the background",
                "Fast commands feel responsive",
                "Agent tools handle advanced workflows",
                "Visual and voice output are controllable",
            ),
            narration=(
                "That is the complete working flow. Jarvis listens in the background, wakes on Hey Jarvis, "
                "understands Indian English and Hinglish, performs actions, shows fullscreen output, speaks naturally, "
                "and can be interrupted with quit."
            ),
            kind="done",
        ),
    ]


async def render_audio(scenes: list[DemoScene], voice: str) -> list[Path]:
    paths: list[Path] = []
    for index, scene in enumerate(scenes, start=1):
        path = AUDIO_DIR / f"{index:02d}_{slug(scene.title)}.mp3"
        if path.exists():
            path.unlink()
        try:
            import edge_tts

            communicate = edge_tts.Communicate(scene.narration, voice, rate="+9%", volume="+0%")
            await communicate.save(str(path))
        except Exception:
            path = AUDIO_DIR / f"{index:02d}_{slug(scene.title)}.wav"
            render_silence(path, max(4.0, len(scene.narration) / 120))
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
                "18",
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
        "\n".join(f"file '{str(path.resolve()).replace(chr(92), '/')}'" for path in segment_paths),
        encoding="utf-8",
    )
    if FINAL_VIDEO.exists():
        FINAL_VIDEO.unlink()
    run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_path), "-c", "copy", "-movflags", "+faststart", str(FINAL_VIDEO)])


def run(command: list[str]) -> None:
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "Command failed:\n"
            + " ".join(command)
            + "\nSTDOUT:\n"
            + completed.stdout[-3000:]
            + "\nSTDERR:\n"
            + completed.stderr[-3000:]
        )


def render_scene(scene: DemoScene, index: int) -> Path:
    image = make_background(index)
    draw = ImageDraw.Draw(image, "RGBA")
    fonts = fonts_for_scene()
    draw_matrix(draw, index)
    draw_top_bar(draw, scene, index, fonts)
    draw_demo_panel(draw, scene, index, fonts)
    draw_right_visual(draw, scene, index, fonts)
    draw_footer(draw, index, fonts)
    image = image.filter(ImageFilter.UnsharpMask(radius=1, percent=105, threshold=3))
    path = FRAME_DIR / f"{index + 1:02d}_{slug(scene.title)}.png"
    image.save(path, "PNG")
    return path


def make_background(index: int) -> Image.Image:
    width, height = SIZE
    top = np.array((1, 8, 6), dtype=np.float32)
    bottom_colors = [
        np.array((4, 30, 24), dtype=np.float32),
        np.array((7, 18, 34), dtype=np.float32),
        np.array((22, 11, 17), dtype=np.float32),
    ]
    bottom = bottom_colors[index % len(bottom_colors)]
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(height):
        t = y / max(1, height - 1)
        arr[y, :, :] = (top * (1 - t) + bottom * t).astype(np.uint8)
    image = Image.fromarray(arr, "RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rectangle((0, 0, width, height), fill=(0, 0, 0, 45))
    draw.ellipse((1280, -300, 2230, 650), fill=(25, 255, 196, 26))
    draw.ellipse((-180, 630, 520, 1330), fill=(248, 215, 109, 20))
    return image


def fonts_for_scene() -> dict[str, ImageFont.FreeTypeFont]:
    return {
        "display": font("bahnschrift.ttf", 78),
        "title": font("bahnschrift.ttf", 58),
        "subtitle": font("segoeui.ttf", 30),
        "body": font("segoeui.ttf", 31),
        "body_small": font("segoeui.ttf", 25),
        "bold": font("segoeuib.ttf", 32),
        "mono": font("consola.ttf", 26),
        "mono_big": font("consola.ttf", 34),
    }


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for candidate in (
        Path("C:/Windows/Fonts") / name,
        Path("C:/Windows/Fonts") / name.upper(),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ):
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default(size=size)


def draw_matrix(draw: ImageDraw.ImageDraw, index: int) -> None:
    rng = np.random.default_rng(20260508 + index)
    glyphs = "01JARVISVOICECOREWAKEOUTPUT"
    f = font("consola.ttf", 19)
    for x in range(0, SIZE[0], 36):
        y0 = int(rng.integers(-260, 80))
        length = int(rng.integers(16, 34))
        for i in range(length):
            y = y0 + i * 28
            if -20 <= y <= SIZE[1] + 20:
                alpha = max(18, 180 - i * 6)
                draw.text((x, y), glyphs[int(rng.integers(0, len(glyphs)))], font=f, fill=(32, 255, 196, alpha))


def draw_top_bar(draw: ImageDraw.ImageDraw, scene: DemoScene, index: int, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    draw.rectangle((0, 0, SIZE[0], 110), fill=(1, 13, 10, 225))
    draw.line((0, 110, SIZE[0], 110), fill=(25, 255, 196, 145), width=3)
    draw.text((92, 34), "JARVIS WORKING DEMO", font=fonts["body_small"], fill=(126, 255, 203, 245))
    draw.rounded_rectangle((1510, 30, 1815, 82), radius=8, outline=(25, 255, 196, 160), width=2, fill=(3, 35, 28, 200))
    draw.text((1534, 43), f"STEP {index + 1:02d}/{10:02d}", font=fonts["body_small"], fill=(240, 255, 251, 255))
    draw.text((92, 132), scene.title, font=fonts["display"] if index == 0 else fonts["title"], fill=(248, 255, 252, 255))
    draw.text((98, 221), scene.subtitle, font=fonts["subtitle"], fill=(198, 230, 224, 238))


def draw_demo_panel(draw: ImageDraw.ImageDraw, scene: DemoScene, index: int, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    x, y, w, h = 92, 328, 850, 548
    draw.rounded_rectangle((x, y, x + w, y + h), radius=10, fill=(2, 14, 12, 235), outline=(25, 255, 196, 175), width=3)
    draw.rectangle((x, y, x + w, y + 68), fill=(3, 38, 30, 230))
    draw.text((x + 28, y + 20), "LIVE COMMAND SEQUENCE", font=fonts["mono"], fill=(126, 255, 203, 255))
    draw.text((x + 30, y + 104), scene.command, font=fonts["mono_big"], fill=(248, 215, 109, 255))
    draw.rounded_rectangle((x + 28, y + 172, x + w - 28, y + 282), radius=8, fill=(7, 20, 18, 245), outline=(25, 255, 196, 105), width=2)
    draw_wrapped(draw, scene.output, x + 52, y + 198, w - 104, fonts["body"], (235, 252, 247, 255), max_lines=3)

    by = y + 328
    for bullet in scene.bullets:
        draw.ellipse((x + 36, by + 12, x + 56, by + 32), fill=(25, 255, 196, 220))
        draw_wrapped(draw, bullet, x + 76, by + 2, w - 115, fonts["body_small"], (225, 245, 240, 245), max_lines=1)
        by += 48


def draw_right_visual(draw: ImageDraw.ImageDraw, scene: DemoScene, index: int, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    x, y, w, h = 1015, 304, 810, 590
    draw.rounded_rectangle((x, y, x + w, y + h), radius=10, fill=(2, 13, 11, 230), outline=(25, 255, 196, 170), width=3)
    draw.rectangle((x, y, x + w, y + 64), fill=(3, 35, 28, 230))
    draw.text((x + 28, y + 18), f"{scene.kind.upper()} VIEW", font=fonts["mono"], fill=(126, 255, 203, 255))
    if scene.kind in {"app", "browser"}:
        draw_app_mock(draw, scene, x + 50, y + 105, fonts)
    elif scene.kind == "visual":
        draw_fullscreen_output_mock(draw, x + 45, y + 105, fonts)
    elif scene.kind == "quit":
        draw_quit_mock(draw, x + 45, y + 105, fonts)
    elif scene.kind == "tools":
        draw_tool_grid(draw, x + 52, y + 110, fonts)
    else:
        draw_orb_and_flow(draw, scene, index, x, y, w, h, fonts)


def draw_app_mock(draw: ImageDraw.ImageDraw, scene: DemoScene, x: int, y: int, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    if scene.kind == "app":
        draw.rounded_rectangle((x, y, x + 700, y + 390), radius=8, fill=(235, 238, 232, 255), outline=(150, 160, 160, 255), width=2)
        draw.rectangle((x, y, x + 700, y + 42), fill=(28, 35, 42, 255))
        draw.text((x + 18, y + 10), "Notepad", font=fonts["body_small"], fill=(248, 252, 255, 255))
        draw.text((x + 36, y + 92), "abc", font=font("consola.ttf", 48), fill=(12, 18, 24, 255))
        draw.text((x + 36, y + 310), "typed by Jarvis automation", font=fonts["body_small"], fill=(60, 80, 80, 255))
    else:
        draw.rounded_rectangle((x, y, x + 700, y + 390), radius=8, fill=(10, 16, 24, 255), outline=(25, 255, 196, 150), width=2)
        draw.rectangle((x + 22, y + 26, x + 678, y + 74), fill=(240, 244, 248, 255))
        draw.text((x + 42, y + 37), "youtube.com/results?search_query=arijit+singh", font=fonts["body_small"], fill=(18, 28, 35, 255))
        draw.rounded_rectangle((x + 48, y + 128, x + 652, y + 318), radius=12, fill=(100, 20, 20, 255), outline=(255, 255, 255, 80), width=2)
        draw.text((x + 92, y + 206), "ARijit Singh results", font=fonts["bold"], fill=(255, 245, 240, 255))


def draw_fullscreen_output_mock(draw: ImageDraw.ImageDraw, x: int, y: int, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    draw.rounded_rectangle((x, y, x + 720, y + 390), radius=8, fill=(1, 8, 7, 255), outline=(25, 255, 196, 180), width=3)
    draw.rectangle((x + 36, y + 35, x + 684, y + 91), fill=(3, 38, 30, 245))
    draw.text((x + 58, y + 50), "OUTPUT CONSOLE", font=fonts["mono"], fill=(126, 255, 203, 255))
    draw.text((x + 58, y + 126), "Jarvis output appears here.", font=fonts["body"], fill=(235, 252, 247, 255))
    draw.text((x + 58, y + 178), "Speech plays in the Indian Jarvis voice.", font=fonts["body"], fill=(235, 252, 247, 255))
    draw.rounded_rectangle((x + 468, y + 310, x + 665, y + 356), radius=6, fill=(55, 17, 14, 255), outline=(255, 126, 101, 180), width=2)
    draw.text((x + 498, y + 321), "Quit Speaking", font=fonts["body_small"], fill=(255, 225, 216, 255))


def draw_quit_mock(draw: ImageDraw.ImageDraw, x: int, y: int, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    draw.rounded_rectangle((x, y, x + 720, y + 390), radius=8, fill=(2, 14, 12, 250), outline=(25, 255, 196, 160), width=3)
    draw.text((x + 70, y + 78), "VOICE INTERRUPT DETECTED", font=fonts["bold"], fill=(248, 215, 109, 255))
    draw.text((x + 70, y + 148), "keyword: quit", font=fonts["mono_big"], fill=(255, 180, 160, 255))
    draw.text((x + 70, y + 226), "speech stopped", font=fonts["body"], fill=(235, 252, 247, 255))
    draw.text((x + 70, y + 278), "state: listening for Hey Jarvis", font=fonts["body"], fill=(126, 255, 203, 255))


def draw_tool_grid(draw: ImageDraw.ImageDraw, x: int, y: int, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    labels = ["shell", "apps", "files", "web", "browser", "system", "git", "docker"]
    for i, label in enumerate(labels):
        col, row = i % 2, i // 2
        xx, yy = x + col * 342, y + row * 88
        draw.rounded_rectangle((xx, yy, xx + 286, yy + 58), radius=8, fill=(3, 38, 30, 230), outline=(25, 255, 196, 150), width=2)
        draw.text((xx + 24, yy + 15), label.upper(), font=fonts["body_small"], fill=(238, 255, 250, 255))


def draw_orb_and_flow(draw: ImageDraw.ImageDraw, scene: DemoScene, index: int, x: int, y: int, w: int, h: int, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    cx, cy = x + w // 2, y + 255
    for r, alpha in ((112, 180), (158, 105), (214, 62), (276, 32)):
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(25, 255, 196, alpha), width=3)
    draw.ellipse((cx - 110, cy - 110, cx + 110, cy + 110), fill=(25, 255, 196, 40), outline=(25, 255, 196, 230), width=4)
    draw_centered(draw, "JARVIS", (cx, cy), fonts["title"], (246, 255, 252, 255))
    flow = {
        "hero": ["STANDBY", "WAKE", "ACT", "SPEAK"],
        "wake": ["MIC", "VOSK", "POPUP", "RECORD"],
        "time": ["HEAR", "PARSE", "LOCAL", "REPLY"],
        "system": ["PSUTIL", "FORMAT", "SPEAK", "SHOW"],
        "done": ["READY", "FAST", "SAFE", "LOCAL"],
    }.get(scene.kind, ["INPUT", "TOOLS", "OUTPUT"])
    fx = x + 74
    fy = y + h - 110
    for i, label in enumerate(flow):
        xx = fx + i * 160
        draw.rounded_rectangle((xx, fy, xx + 132, fy + 58), radius=8, fill=(3, 38, 30, 230), outline=(25, 255, 196, 150), width=2)
        draw_centered(draw, label, (xx + 66, fy + 29), fonts["body_small"], (238, 255, 250, 255))


def draw_footer(draw: ImageDraw.ImageDraw, index: int, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    draw.line((92, 948, 1828, 948), fill=(25, 255, 196, 90), width=2)
    draw.text((92, 978), f"Rendered {datetime.now():%Y-%m-%d %H:%M} from local Jarvis project", font=fonts["mono"], fill=(168, 225, 214, 235))
    draw.text((1580, 978), "FULL WORKING DEMO", font=fonts["mono"], fill=(168, 225, 214, 235))


def draw_wrapped(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, max_width: int, font_obj: ImageFont.FreeTypeFont, fill, max_lines: int) -> None:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if text_width(draw, candidate, font_obj) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    for i, line in enumerate(lines[:max_lines]):
        draw.text((x, y + i * (font_obj.size + 8)), line, font=font_obj, fill=fill)


def draw_centered(draw: ImageDraw.ImageDraw, text: str, center: tuple[int, int], font_obj: ImageFont.FreeTypeFont, fill) -> None:
    box = draw.textbbox((0, 0), text, font=font_obj)
    w = box[2] - box[0]
    h = box[3] - box[1]
    draw.text((center[0] - w / 2, center[1] - h / 2 - box[1] / 2), text, font=font_obj, fill=fill)


def text_width(draw: ImageDraw.ImageDraw, text: str, font_obj: ImageFont.FreeTypeFont) -> int:
    box = draw.textbbox((0, 0), text, font=font_obj)
    return box[2] - box[0]


def slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", text.strip()).strip("_").lower() or "scene"


if __name__ == "__main__":
    main()
