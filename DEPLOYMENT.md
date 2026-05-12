# Deployment Guide

Jarvis is a local Windows desktop voice assistant. Deploying it means installing it on a Windows machine that has Python, a microphone, and access to the local apps/files you want Jarvis to control.

It is not currently a web server, so platforms like Vercel, Render, Railway, or Netlify cannot run the full voice assistant as-is. To deploy it to those platforms, the project would first need to be split into a web/API service and a separate local desktop client.

## Recommended Deployment

### 1. Publish the Source

Use GitHub or another private Git host for the source code.

Before pushing, make sure these stay out of Git:

- `.env`
- `.venv/`
- `data/`
- `models/`
- runtime logs, locks, and temporary files
- downloaded model files

The existing `.gitignore` is already set up for those files.

```powershell
git init
git add .
git commit -m "Prepare Jarvis assistant for deployment"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### 2. Install on the Target Windows PC

On the target PC, install:

- Windows 10 or 11
- Python 3.11+ for Windows from python.org
- Git
- A working microphone
- Optional: Ollama, if you want local model fallback

Avoid MSYS2/Git Bash Python for deployment. This project expects the normal Windows virtual environment layout at `.venv\Scripts\python.exe`.

Clone the project:

```powershell
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO
```

Run the installer:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install_windows.ps1
```

The installer creates `.venv`, installs Python packages, installs the local package entry point, creates `.env` from `.env.example`, and downloads the Vosk wake-word model.

### 3. Configure Secrets

Edit `.env` on the target PC.

For Gemini:

```env
JARVIS_LLM_PROVIDER=gemini
JARVIS_VOICE_LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
MODEL=gemini-2.5-flash
GEMINI_MODEL=gemini-2.5-flash
```

For Ollama fallback:

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:1b
JARVIS_OLLAMA_BACKUP=true
JARVIS_VOICE_OLLAMA_BACKUP=true
```

If you use Ollama, pull the model:

```powershell
ollama pull llama3.2:1b
```

### 4. Verify the Install

Run the deployment validator:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/validate_deployment.ps1
```

The validator runs the readiness check and the unit tests. You can run only the readiness check when diagnosing a target machine:

```powershell
.\.venv\Scripts\python.exe -m jarvis_assistant --doctor
```

Check CLI mode:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_cli.ps1
```

Check localhost mode:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_server.ps1
```

Open `http://127.0.0.1:8765` and run a simple command such as `what is 2 plus 2`.

Check voice mode:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_voice.ps1
```

### 5. Run in the Background

Start Jarvis hidden in the background:

```powershell
powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File scripts/start_jarvis_voice_hidden.ps1
```

Stop it:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/stop_jarvis.ps1
```

### 6. Optional Startup Deployment

Install Jarvis as a startup task for the current Windows user:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install_autostart.ps1
```

Remove the startup task:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/uninstall_autostart.ps1
```

## Deployment Health Checklist

- `powershell -ExecutionPolicy Bypass -File scripts/validate_deployment.ps1` passes.
- `.env` exists on the deployed machine.
- `GEMINI_API_KEY` is set if using Gemini.
- The Vosk model exists at `models/vosk-model-small-en-us-0.15`.
- The correct microphone device is configured in `.env`.
- Jarvis is run as a normal user, not Administrator, unless elevated automation is intentional.
- Background mode can be stopped with `scripts/stop_jarvis.ps1`.

## Cloud Deployment Notes

The current app depends on local Windows features:

- microphone input
- desktop popups
- text-to-speech output
- app launching
- shell and file automation
- local wake-word detection

Those features require a local machine. A cloud deployment would only make sense for a redesigned backend, for example:

- a FastAPI service for text commands
- a browser or mobile frontend
- a local Windows agent that connects to the cloud service
- cloud-hosted memory or task sync

Until that redesign exists, the production deployment target should be a Windows PC.
