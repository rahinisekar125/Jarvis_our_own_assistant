# Jarvis - Local Windows Voice Assistant

Jarvis is a local-first Python voice assistant for Windows. It listens for the wake phrase `Hey Jarvis`, opens a fullscreen cyber-style listening UI, understands Indian English and Hinglish commands, executes safe local tools, shows results in a fullscreen output console, and speaks back using an Indian voice.

The project is designed as a modular AI agent, not a single script. Wake word, speech recognition, LLM routing, tools, safety, memory, text-to-speech, and visual output are separated so new capabilities can be added cleanly.

## Current Features

- Wake phrase: only `Hey Jarvis`
- Offline wake detection with Vosk
- Command speech-to-text with `faster-whisper`
- Indian English and Hinglish tuning with hotwords like `kholo`, `batao`, `chalao`, `likho`, and `dhoondo`
- Gemini primary LLM with retry/backoff handling
- Ollama local backup support
- JSON-style agent tool decisions
- Fast local intents for common commands like time, battery, app opening, search, media, and simple math
- Tools for shell, app launching, files, browser, web search, system info, git, Docker, deployment, and task workflows
- Safety layer for risky commands and file access
- SQLite memory for recent context and preferences
- Edge TTS with Indian voice: `en-IN-PrabhatNeural`
- Fullscreen wake and output popups
- Popup close, `Q`, `Esc`, `Quit Speaking`, or voice command `quit` stops speech
- Background supervisor and stop script for Windows

## Project Structure

```text
jarvis_assistant/
  agent/          LLM manager, prompts, schemas, memory, fast intents
  audio/          wake word, STT, TTS, audio input, model loaders
  executor/       tool execution and safety policy
  tools/          shell, files, system, browser, web, project tools
  ui/             fullscreen popup output windows
  main.py         CLI, voice loop, and supervisor entrypoint
configs/         example YAML config
scripts/         install, run, stop, autostart, and demo video scripts
tests/           unit tests
data/            runtime logs and memory, ignored by Git
models/          downloaded Vosk model, ignored by Git
outputs/         generated videos, ignored by Git
```

## Requirements

- Windows 10 or 11
- Python 3.11+
- Working microphone
- Optional: Ollama for local backup
- Optional: Gemini API key for cloud reasoning

## Quick Start

Open PowerShell in the project folder:

```powershell
cd "C:\path\to\Jarvis_our_own_assistant-main"
powershell -ExecutionPolicy Bypass -File scripts/install_windows.ps1
```

The installer creates `.venv`, installs dependencies, installs the local package entry point, copies `.env.example` to `.env`, and downloads the small Vosk wake-word model if it is missing.

Edit `.env` and add your own keys:

```env
GEMINI_API_KEY=your_key_here
MODEL=gemini-2.5-flash
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:1b
```

Never commit `.env`. It is ignored by Git.

Validate the deployment:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/validate_deployment.ps1
```

You can also run only the readiness check:

```powershell
.\.venv\Scripts\python.exe -m jarvis_assistant --doctor
```

## Run Jarvis

CLI mode:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_cli.ps1
```

Localhost check:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_server.ps1
```

Then open:

```text
http://127.0.0.1:8765
```

Or double-click `RUN_JARVIS_LOCALHOST.bat`.

Public-safe web mode:

```powershell
python -m jarvis_assistant --mode server --host 0.0.0.0 --port 8765 --public
```

Use this mode for cloud hosting. It disables desktop, shell, file, browser, microphone, and voice automation so the public site cannot control the host machine. See `PUBLIC_DEPLOYMENT.md`.

Voice mode in the current terminal:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_voice.ps1
```

Background voice mode:

```powershell
powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File scripts/start_jarvis_voice_hidden.ps1
```

Stop all Jarvis background processes:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/stop_jarvis.ps1
```

Or use:

```powershell
RUN_JARVIS_BACKGROUND.bat
STOP_JARVIS.bat
```

## Wake and Voice Flow

1. Say `Hey Jarvis`.
2. Jarvis opens the fullscreen listening popup.
3. Speak a command.
4. Jarvis executes the action or answers.
5. The result appears in a fullscreen output popup.
6. Jarvis speaks the result.
7. Say `quit`, press `Q`, press `Esc`, close the popup, or click `Quit Speaking` to stop speech.
8. Jarvis returns to wake listening.

## Example Commands

```text
Hey Jarvis, time batao
Hey Jarvis, battery status batao
Hey Jarvis, open notepad and type abc
Hey Jarvis, chrome kholo
Hey Jarvis, Arijit Singh chalao
Hey Jarvis, search Python logging
Hey Jarvis, project status
Hey Jarvis, docker ps
Hey Jarvis, open today's tasks
quit
```

## Configuration

Most settings are controlled by `.env`.

Important values:

```env
JARVIS_WAKE_ALIASES=hey jarvis
JARVIS_STT_ENGINE=whisper
WHISPER_MODEL=base
WHISPER_LANGUAGE=en
JARVIS_SILENCE_SECONDS=0.32
JARVIS_MAX_RECORD_SECONDS=5
JARVIS_SPEECH_START_TIMEOUT_SECONDS=1.2
JARVIS_TTS_BACKEND=edge
JARVIS_TTS_VOICE=en-IN-PrabhatNeural
JARVIS_VISUAL_SHOW_WAKE=true
JARVIS_VISUAL_SHOW_FINAL=true
```

YAML defaults are available in:

```text
configs/config.example.yaml
```

Environment variables override YAML values.

## LLM Reliability

Jarvis uses a reliability layer:

- Retries transient Gemini errors
- Handles rate limits and service failures
- Uses cooldown between requests
- Can switch to Ollama backup
- Falls back to local rule-based behavior only after configured routes fail

For local backup:

```powershell
ollama pull llama3.2:1b
```

## Security Model

Jarvis can run real local actions, so it includes guardrails:

- Shell commands are validated before execution
- Dangerous command patterns are blocked
- File access is limited to allowed paths
- High-risk operations can require confirmation
- Runtime logs are written to `data/logs`

This is not a hard OS sandbox. Run Jarvis as a normal user, not Administrator, unless you intentionally need elevated automation.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Current expected result:

```text
Ran 25 tests
OK
```

## Demo Videos

The checked-in working demo video is:

```text
outputs/jarvis_working_demo/Jarvis_Working_Demo.mp4
```

Generate the feature explainer:

```powershell
.\.venv\Scripts\python.exe scripts/render_jarvis_explainer_video.py --clean
```

Generate the working demo:

```powershell
.\.venv\Scripts\python.exe scripts/render_jarvis_working_demo_video.py --clean
```

Videos are written to `outputs/`. The generated demo outputs are included in this repository so the GitHub project shows the visual demos.

## GitHub Deployment Checklist

Before pushing:

- Confirm `.env` is not staged
- Confirm `.env`, `.venv`, runtime logs, memory DBs, downloaded models, and temp files are not staged
- Run the deployment validator
- Commit source files, scripts, config examples, README, requirements, and tests

Recommended commands:

```powershell
git status
powershell -ExecutionPolicy Bypass -File scripts/validate_deployment.ps1
git add .
git commit -m "Prepare Jarvis assistant for deployment"
git push origin main
```

## Add a New Tool

Create a function that returns `ToolResult`, then register it in `jarvis_assistant/tools/defaults.py`.

```python
registry.register(
    ToolSpec(
        name="my_tool",
        description="Does one focused action.",
        parameters={"value": "string"},
        handler=my_handler,
    )
)
```

The agent automatically sees registered tools in its prompt.
