from __future__ import annotations

import json
import logging
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlparse

from .agent.fast_intents import match_fast_intent
from .doctor import build_checks
from .executor.executor import ConfirmationProvider
from .main import build_runtime

LOGGER = logging.getLogger(__name__)


class DeclineConfirmationProvider(ConfirmationProvider):
    def confirm(self, prompt: str) -> bool:
        LOGGER.warning("Declined interactive confirmation in localhost server: %s", prompt)
        return False


def run_local_server(settings, host: str = "127.0.0.1", port: int = 8765, public: bool = False) -> int:
    runtime = None if public else build_runtime(settings, enable_voice_prompts=False)
    if runtime is not None:
        runtime.agent.executor.confirmer = DeclineConfirmationProvider()

    class JarvisHandler(BaseHTTPRequestHandler):
        server_version = "JarvisLocalHTTP/0.1"

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API.
            path = self._path()
            if path in {"/", "/index.html"}:
                self._send_html(_index_html(public=public))
                return
            if path == "/health":
                if public:
                    self._send_json(
                        {
                            "ok": True,
                            "mode": "public",
                            "checks": [
                                {
                                    "name": "Public web demo",
                                    "ok": True,
                                    "warning": False,
                                    "detail": "Desktop, shell, file, browser, and voice automation are disabled.",
                                }
                            ],
                        }
                    )
                    return
                checks = build_checks(settings)
                self._send_json(
                    {
                        "ok": all(check.ok or check.warning for check in checks),
                        "checks": [
                            {
                                "name": check.name,
                                "ok": check.ok,
                                "warning": check.warning,
                                "detail": check.detail,
                            }
                            for check in checks
                        ],
                    }
                )
                return
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

        def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API.
            if self._path() == "/health":
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                return
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()

        def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API.
            self.send_response(HTTPStatus.NO_CONTENT)
            self._send_cors_headers()
            self.send_header("Access-Control-Allow-Methods", "GET, POST, HEAD, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API.
            if self._path() != "/command":
                self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return

            try:
                payload = self._read_json()
                text = str(payload.get("text", "")).strip()
                if not text:
                    self._send_json({"ok": False, "response": "Text command is required."}, status=HTTPStatus.BAD_REQUEST)
                    return
                if public:
                    self._send_json(_process_public_command(text))
                    return
                if runtime is None:
                    raise RuntimeError("Local runtime is not initialized")
                result = runtime.agent.process(text)
                self._send_json(
                    {
                        "ok": result.ok,
                        "response": result.response,
                        "tool_results": [
                            {
                                "tool": item.tool,
                                "ok": item.ok,
                                "content": item.content,
                                "data": item.data,
                            }
                            for item in result.tool_results
                        ],
                    }
                )
            except Exception as exc:  # noqa: BLE001 - HTTP response should explain failures.
                LOGGER.exception("Localhost command failed")
                self._send_json(
                    {"ok": False, "response": f"Server error: {exc}"},
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                )

        def log_message(self, format: str, *args: Any) -> None:
            LOGGER.info("localhost %s", format % args)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError("JSON body must be an object")
            return data

        def _path(self) -> str:
            path = urlparse(self.path).path or "/"
            if path != "/":
                path = path.rstrip("/")
            return path

        def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._send_cors_headers()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, html: str) -> None:
            body = html.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_cors_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*" if public else "http://127.0.0.1:%s" % port)

    httpd = ThreadingHTTPServer((host, port), JarvisHandler)
    label = "public-safe" if public else "localhost"
    print(f"Jarvis {label} server running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
        return 0
    finally:
        httpd.server_close()
    return 0


def _process_public_command(text: str) -> dict[str, Any]:
    decision = match_fast_intent(text)
    if decision is not None and not decision.tool_calls:
        return {"ok": True, "response": decision.message or "Done.", "tool_results": []}

    if decision is not None and decision.tool_calls:
        tool_names = ", ".join(call.tool for call in decision.tool_calls)
        return {
            "ok": False,
            "response": (
                "This public demo is online, but desktop automation is disabled for safety. "
                f"That command would need local tool access: {tool_names}."
            ),
            "tool_results": [],
        }

    ai_response = _public_ai_answer(text)
    if ai_response:
        return {"ok": True, "response": ai_response, "tool_results": []}

    fallback = _public_fallback_answer(text)
    if fallback:
        return {"ok": True, "response": fallback, "tool_results": []}

    return {
        "ok": True,
        "response": (
            "Jarvis public demo is running, but the full public text brain is not configured yet. "
            "Add GEMINI_API_KEY in Render environment variables for richer answers. "
            "I can still answer safe local demo commands like 'what is 2 plus 2', 'time batao', "
            "'what is JS', or 'who are you'."
        ),
        "tool_results": [],
    }


def _public_ai_answer(text: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return ""

    model = os.getenv("MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash")).strip() or "gemini-2.5-flash"
    prompt = (
        "You are Jarvis, a public-safe web demo of a Windows voice assistant. "
        "Answer the user's text question helpfully and concisely. "
        "Do not claim you can access this server's desktop, files, microphone, browser, shell, apps, or private data. "
        "If the user asks for a local desktop action, explain that it works only in local Windows mode.\n\n"
        f"User: {text}"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 512},
    }
    request = Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        return str(data["candidates"][0]["content"]["parts"][0]["text"]).strip()
    except (HTTPError, URLError, KeyError, IndexError, TimeoutError, json.JSONDecodeError) as exc:
        LOGGER.warning("Public Gemini answer unavailable: %s", exc)
        return ""


def _public_fallback_answer(text: str) -> str:
    clean = " ".join(text.strip().split())
    lowered = clean.lower().rstrip("?.!")

    topic = _extract_definition_topic(lowered)
    if topic:
        definitions = {
            "ai": "AI, or artificial intelligence, is software that can perform tasks that usually need human-like reasoning, such as understanding language, recognizing patterns, and making decisions.",
            "api": "An API is a set of rules that lets one software system talk to another. Apps use APIs to request data, trigger actions, or connect services.",
            "css": "CSS, or Cascading Style Sheets, is the language used to style web pages: colors, spacing, layouts, fonts, and responsive design.",
            "html": "HTML is the markup language used to structure web pages. It defines elements like headings, paragraphs, buttons, links, images, and forms.",
            "jarvis": "Jarvis is this project: a local Windows assistant that can listen for a wake phrase, understand text or voice commands, and safely run desktop tools.",
            "js": "JS usually means JavaScript. It is the programming language used to make websites interactive, run browser logic, call APIs, and build many web apps.",
            "javascript": "JavaScript is a programming language used mainly for web interactivity, backend services with Node.js, mobile apps, and many modern full-stack projects.",
            "python": "Python is a popular programming language known for readable syntax. It is widely used for automation, AI, data work, web backends, and scripting.",
            "render": "Render is a cloud hosting platform for web services, static sites, background workers, cron jobs, databases, and deploys from Git repositories.",
        }
        if topic in definitions:
            return definitions[topic]
        return (
            f"{topic.upper() if len(topic) <= 3 else topic.title()} is a topic I can explain better once "
            "GEMINI_API_KEY is configured on the public deployment. Right now this demo has a small offline fallback brain."
        )

    if lowered in {"hello jarvis", "hello", "hi", "hey"}:
        return "Hello. Jarvis public demo is online. Ask me a safe text question, or try the local Windows app for voice and desktop control."

    if "demo video" in lowered or "working demo" in lowered:
        return "The demo video shows the local Windows version: wake word, voice input, fullscreen output, app control, browser actions, and speech. The public site is text-only for safety."

    return ""


def _extract_definition_topic(text: str) -> str:
    patterns = [
        r"^(?:what is|what's|what are|define|explain|tell me about)\s+(?P<topic>.+)$",
        r"^(?P<topic>.+)\s+(?:kya hai|means what)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, text)
        if match:
            topic = match.group("topic").strip().strip("'\"")
            aliases = {"java script": "javascript", "node js": "node.js"}
            return aliases.get(topic, topic)
    return ""


def _index_html(public: bool = False) -> str:
    title = "Jarvis Public Demo" if public else "Jarvis Local Check"
    status = "Checking public demo..." if public else "Checking localhost..."
    intro = (
        "Public-safe cloud mode is running. Desktop automation, shell, files, browser control, voice, and wake-word features are disabled."
        if public
        else "Send a text command to the local assistant server. Voice mode, wake word, and desktop automation still run from the Windows scripts."
    )
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  <style>
    :root { color-scheme: dark; font-family: "Segoe UI", Arial, sans-serif; }
    body { margin: 0; min-height: 100vh; background: #07110f; color: #eef7f4; }
    main { width: min(880px, calc(100% - 32px)); margin: 0 auto; padding: 40px 0; }
    h1 { margin: 0 0 8px; font-size: clamp(32px, 5vw, 56px); letter-spacing: 0; }
    p { color: #a8c7be; font-size: 16px; line-height: 1.5; }
    section { border: 1px solid #1f6f62; border-radius: 8px; padding: 18px; margin-top: 22px; background: #0b1d19; }
    textarea { width: 100%; min-height: 104px; resize: vertical; box-sizing: border-box; border: 1px solid #2b8b7b; border-radius: 8px; padding: 12px; background: #04100e; color: #eef7f4; font-size: 16px; }
    button { margin-top: 12px; border: 0; border-radius: 8px; padding: 10px 16px; background: #25d6b2; color: #03110e; font-weight: 700; cursor: pointer; }
    button:disabled { opacity: .65; cursor: wait; }
    pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #030807; border: 1px solid #174a42; border-radius: 8px; padding: 14px; min-height: 80px; }
    .status { display: inline-flex; gap: 8px; align-items: center; padding: 6px 10px; border-radius: 999px; background: #12352f; color: #b6f7e9; }
  </style>
</head>
<body>
  <main>
    <div class="status" id="status">__STATUS__</div>
    <h1>__TITLE__</h1>
    <p>__INTRO__</p>
    <section>
      <textarea id="command">what is 2 plus 2</textarea>
      <button id="send">Run Command</button>
      <pre id="output">Waiting for command...</pre>
    </section>
    <section>
      <button id="health">Refresh Health</button>
      <pre id="healthOutput">Health not loaded yet.</pre>
    </section>
  </main>
  <script>
    const statusEl = document.querySelector("#status");
    const outputEl = document.querySelector("#output");
    const healthEl = document.querySelector("#healthOutput");
    const sendButton = document.querySelector("#send");
    const healthButton = document.querySelector("#health");

    async function loadHealth() {
      healthButton.disabled = true;
      try {
        const response = await fetch("/health");
        const data = await response.json();
        statusEl.textContent = data.ok ? "Localhost server online" : "Localhost server has setup issues";
        healthEl.textContent = JSON.stringify(data, null, 2);
      } catch (error) {
        statusEl.textContent = "Localhost server error";
        healthEl.textContent = String(error);
      } finally {
        healthButton.disabled = false;
      }
    }

    async function runCommand() {
      sendButton.disabled = true;
      outputEl.textContent = "Working...";
      try {
        const text = document.querySelector("#command").value;
        const response = await fetch("/command", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text })
        });
        const data = await response.json();
        outputEl.textContent = JSON.stringify(data, null, 2);
      } catch (error) {
        outputEl.textContent = String(error);
      } finally {
        sendButton.disabled = false;
      }
    }

    sendButton.addEventListener("click", runCommand);
    healthButton.addEventListener("click", loadHealth);
    loadHealth();
  </script>
</body>
</html>"""
    return html.replace("__TITLE__", title).replace("__STATUS__", status).replace("__INTRO__", intro)
