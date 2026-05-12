# Public Deployment

This project is a Windows desktop voice assistant. The full assistant should not be exposed directly to the public internet because it can launch apps, read and write files, and run shell commands.

For public hosting, use the public-safe web mode:

```powershell
python -m jarvis_assistant --mode server --host 0.0.0.0 --port 8765 --public
```

Public mode keeps the web UI and safe text responses online, but disables desktop automation, shell commands, file access, browser control, microphone input, wake-word detection, and text-to-speech.

## Render

1. Push this project to GitHub.
2. Create a new Render web service from the repo.
3. Use the included `render.yaml`, or set:
   - Build command: `pip install -r requirements-public.txt`
   - Start command: `python -m jarvis_assistant --mode server --host 0.0.0.0 --port $PORT --public`
4. Deploy.

## Heroku-Compatible Hosts

The included `Procfile` starts public-safe mode:

```text
web: python -m jarvis_assistant --mode server --host 0.0.0.0 --port $PORT --public
```

## What Works Publicly

- Health endpoint: `/health`
- Web page: `/`
- Safe text endpoint: `/command`
- Examples: `what is 2 plus 2`, `time batao`, `who are you`

## What Requires Local Windows

- Wake word: `Hey Jarvis`
- Microphone speech recognition
- Fullscreen desktop UI
- App launching
- Browser control
- Shell, file, Git, Docker, and project automation
- Text-to-speech output
