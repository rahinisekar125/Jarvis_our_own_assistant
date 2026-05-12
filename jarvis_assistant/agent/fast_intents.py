from __future__ import annotations

import ast
import operator
import re
import urllib.parse
from datetime import datetime

from .language import prefers_hinglish
from .schemas import AgentDecision, ToolCall

_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_BROWSER_SHORTCUTS = {
    "chat gpt": "https://chatgpt.com/",
    "chatgpt": "https://chatgpt.com/",
    "clickup": "https://app.clickup.com/",
    "gmail": "https://mail.google.com/",
    "google": "https://www.google.com/",
    "github": "https://github.com/",
    "linkedin": "https://www.linkedin.com/",
    "whatsapp": "https://web.whatsapp.com/",
    "youtube": "https://www.youtube.com/",
}

_KNOWN_APP_NAMES = {
    "brave",
    "calculator",
    "calc",
    "chrome",
    "code",
    "cmd",
    "edge",
    "excel",
    "explorer",
    "firefox",
    "notepad",
    "onenote",
    "outlook",
    "paint",
    "powerpoint",
    "powershell",
    "settings",
    "spotify",
    "terminal",
    "vscode",
    "word",
    "wordpad",
    *set(_BROWSER_SHORTCUTS),
}


def match_fast_intent(user_text: str) -> AgentDecision | None:
    text = " ".join(user_text.lower().strip().split())
    if not text:
        return None

    hinglish_decision = _match_hinglish_intent(user_text)
    if hinglish_decision is not None:
        return hinglish_decision

    if text in {
        "time",
        "what time is it",
        "what is the time",
        "what is the time right now",
        "tell me the time",
        "current time",
        "current time right now",
    }:
        return _final(user_text, f"It is {datetime.now():%I:%M %p}.", f"Abhi {datetime.now():%I:%M %p} hai.")

    if text in {"date", "what date is it", "today's date", "what is today's date"}:
        return _final(
            user_text,
            f"Today is {datetime.now():%A, %B %d, %Y}.",
            f"Aaj {datetime.now():%A, %B %d, %Y} hai.",
        )

    if text in {"stop", "cancel", "never mind", "nevermind", "leave it", "forget it"}:
        return _final(user_text, "Okay, cancelled.", "Theek hai, cancel kar diya.")

    if text in {"hello", "hi", "hey", "hey jarvis", "jarvis"}:
        return _final(user_text, "Hi Ayush, I am listening.", "Hi Ayush, main sun raha hoon.")

    if text in {"thank you", "thanks", "ok thanks", "okay thanks"}:
        return _final(user_text, "You're welcome.", "Welcome, Ayush.")

    if text in {"who are you", "what are you"}:
        return _final(
            user_text,
            "I am Jarvis, your local voice assistant.",
            "Main Jarvis hoon, aapka local voice assistant.",
        )

    if text in {"help", "help me", "what can you do"}:
        return _final(
            user_text,
            "I can open apps and websites, search the web, show system status, list files, and help with git or Docker.",
            "Main apps aur websites khol sakta hoon, web search kar sakta hoon, system status dikha sakta hoon, aur git ya Docker mein help kar sakta hoon.",
        )

    if text in {"tell me something", "say something", "talk to me"}:
        return _final(
            user_text,
            "I am online, Ayush. Ask me to open an app, search the web, check your system, or help with this project.",
            "Main online hoon, Ayush. App kholne, web search, system check, ya project help ke liye boliye.",
        )

    if text in {"give me a tip", "productivity tip", "tell me a productivity tip"}:
        return _final(
            user_text,
            "Pick one task, set a short timer, and finish the smallest useful step first.",
            "Ek task choose karo, short timer lagao, aur sabse chhota useful step pehle complete karo.",
        )

    if text in {"tell me a joke", "say a joke", "joke"}:
        return _final(
            user_text,
            "Why did the developer go broke? Because they used up all their cache.",
            "Developer broke kyun hua? Kyunki usne apna saara cache use kar liya.",
        )

    math_answer = _try_math(text)
    if math_answer is not None:
        if prefers_hinglish(user_text):
            math_answer = math_answer.replace("The answer is", "Answer").rstrip(".") + " hai."
        return AgentDecision(status="final", message=math_answer)

    open_and_type = _match_open_and_type_intent(user_text)
    if open_and_type is not None:
        return open_and_type

    if text.startswith("open "):
        app_name = text.removeprefix("open ").strip()
        if app_name:
            if app_name in {"today tasks", "today's tasks", "tasks", "my tasks"}:
                return _tool("manage_projects", {"action": "open_today_tasks"})
            if app_name in _BROWSER_SHORTCUTS:
                return _open_url(_BROWSER_SHORTCUTS[app_name])
            if _looks_like_url(app_name):
                return _open_url(app_name)
            return _tool("open_application", {"app_name": app_name})

    if ("today" in text or "my" in text) and "task" in text:
        return _tool("manage_projects", {"action": "open_today_tasks"})

    if text in {"git status", "show git status", "project status"}:
        return _tool("manage_projects", {"action": "git_status"})

    if text in {"docker ps", "show docker containers", "list docker containers"}:
        return _tool("manage_projects", {"action": "docker_ps"})

    if text in {"run docker container", "start docker compose", "docker compose up"}:
        return _tool("manage_projects", {"action": "docker_compose_up"})

    if text in {"deploy my project", "deploy project"}:
        return _tool("manage_projects", {"action": "deploy"})

    if text.startswith("play "):
        query = text.removeprefix("play ").strip()
        if query:
            return _open_url(_youtube_search_url(query))

    for prefix in ("search for ", "search ", "web search ", "google ", "look up "):
        if text.startswith(prefix):
            query = text.removeprefix(prefix).strip()
            if query:
                return _tool("web_search", {"query": query})

    if text in {"battery", "battery status", "cpu status", "memory status"}:
        return _tool("get_system_info", {})

    if text in {"system info", "system status", "computer status"}:
        return _tool("get_system_info", {})

    if text in {"list files", "show files", "dir", "directory"}:
        return _tool("run_shell_command", {"command": "dir"})

    if text in {"where am i", "current folder", "current directory", "working directory"}:
        return _tool("run_shell_command", {"command": "cd"})

    return None


def _tool(name: str, arguments: dict) -> AgentDecision:
    return AgentDecision(
        status="tool_call",
        message="Done.",
        tool_calls=[ToolCall(tool=name, arguments=arguments)],
    )


def _final(user_text: str, english: str, hinglish: str) -> AgentDecision:
    return AgentDecision(status="final", message=hinglish if prefers_hinglish(user_text) else english)


def _open_url(url: str) -> AgentDecision:
    return _tool("control_browser", {"action": {"type": "open_url", "url": url}})


def _match_open_and_type_intent(user_text: str) -> AgentDecision | None:
    clean = " ".join(user_text.strip().split())
    match = re.match(
        r"^open\s+(?P<app>.+?)\s+(?:and\s+)?(?:type|write|enter|paste)\s+(?P<text>.+?)"
        r"(?:\s+in\s+(?:that|it|there|the\s+app|the\s+application))?$",
        clean,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    app_name = match.group("app").strip()
    text = _strip_quotes(match.group("text").strip())
    if not app_name or not text:
        return None
    return _tool("open_application_and_type", {"app_name": app_name, "text": text})


def _match_hinglish_intent(user_text: str) -> AgentDecision | None:
    clean = " ".join(user_text.strip().split())
    text = clean.lower()

    if text in {"time batao", "time kya hai", "samay batao", "kitna time hua hai"}:
        return AgentDecision(status="final", message=f"Abhi {datetime.now():%I:%M %p} hai.")

    if text in {"date batao", "aaj ki date batao", "aaj date kya hai"}:
        return AgentDecision(status="final", message=f"Aaj {datetime.now():%A, %B %d, %Y} hai.")

    if text in {"battery batao", "battery status batao", "system status batao"}:
        return _tool("get_system_info", {})

    open_and_type = re.match(
        r"^(?P<app>.+?)\s+(?:khol(?:o|na)?|open\s+karo|chalao)\s+"
        r"(?:aur\s+)?(?:type|likh(?:o|na)?|write|enter)\s+(?P<text>.+?)$",
        clean,
        flags=re.IGNORECASE,
    )
    if open_and_type:
        return _tool(
            "open_application_and_type",
            {
                "app_name": open_and_type.group("app").strip(),
                "text": _strip_quotes(open_and_type.group("text").strip()),
            },
        )

    open_app = re.match(
        r"^(?P<app>.+?)\s+(?P<verb>khol(?:o|na)?|open\s+karo|chalao)$",
        clean,
        flags=re.IGNORECASE,
    )
    if open_app:
        app_name = open_app.group("app").strip()
        if app_name:
            verb = open_app.group("verb").lower()
            if verb == "chalao" and app_name.lower() not in _KNOWN_APP_NAMES:
                return _open_url(_youtube_search_url(app_name))
            if app_name.lower() in _BROWSER_SHORTCUTS:
                return _open_url(_BROWSER_SHORTCUTS[app_name.lower()])
            return _tool("open_application", {"app_name": app_name})

    search = re.match(
        r"^(?:search|google|dhundo|dhoondo)\s+(?:karo\s+|for\s+)?(?P<query>.+?)$",
        clean,
        flags=re.IGNORECASE,
    )
    if search:
        query = search.group("query").strip()
        if query:
            return _tool("web_search", {"query": query})

    play = re.match(
        r"^(?:play|chalao|bajao)\s+(?P<query>.+?)$|^(?P<song>.+?)\s+(?:chalao|bajao)$",
        clean,
        flags=re.IGNORECASE,
    )
    if play:
        query = (play.group("query") or play.group("song") or "").strip()
        if query:
            return _open_url(_youtube_search_url(query))

    return None


def _strip_quotes(text: str) -> str:
    pairs = {
        '"': '"',
        "'": "'",
        "â€œ": "â€",
        "â€˜": "â€™",
    }
    if len(text) >= 2 and text[0] in pairs and text[-1] == pairs[text[0]]:
        text = text[1:-1].strip()

    spoken = text.lower()
    if spoken.startswith("quote ") and spoken.endswith(" quote") and len(text) > 12:
        text = text[6:-6].strip()
    return text


def _looks_like_url(text: str) -> bool:
    first = text.split(" ", 1)[0]
    return "." in first and not first.endswith((".exe", ".cmd", ".bat", ".ps1"))


def _youtube_search_url(query: str) -> str:
    encoded = urllib.parse.quote_plus(query)
    return f"https://www.youtube.com/results?search_query={encoded}"


def _try_math(text: str) -> str | None:
    expression = text
    expression = re.sub(r"^(what is|what's|calculate|compute)\s+", "", expression)
    replacements = {
        " plus ": " + ",
        " minus ": " - ",
        " times ": " * ",
        " multiplied by ": " * ",
        " divided by ": " / ",
        " over ": " / ",
    }
    for source, target in replacements.items():
        expression = expression.replace(source, target)

    if not re.fullmatch(r"[\d\s.+\-*/()%]+", expression):
        return None
    try:
        value = _eval_math(ast.parse(expression, mode="eval").body)
    except Exception:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"The answer is {value}."


def _eval_math(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval_math(node.left), _eval_math(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval_math(node.operand))
    raise ValueError("unsupported expression")
