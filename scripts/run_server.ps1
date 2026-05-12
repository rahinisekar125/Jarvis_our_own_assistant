$ErrorActionPreference = "Stop"

.\.venv\Scripts\Activate.ps1
python -m jarvis_assistant --mode server --host 127.0.0.1 --port 8765
