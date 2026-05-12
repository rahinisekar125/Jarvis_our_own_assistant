from __future__ import annotations

import json
import urllib.parse
import webbrowser
from typing import Any

from ..config import Settings
from .base import ToolResult, ToolSpec


def build_web_tools(_settings: Settings) -> list[ToolSpec]:
    def web_search(query: str, max_results: int = 5) -> ToolResult:
        import requests
        from bs4 import BeautifulSoup

        response = requests.get(
            "https://duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 JarvisLocalAssistant/0.1"},
            timeout=20,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        for item in soup.select(".result"):
            link = item.select_one(".result__a")
            snippet = item.select_one(".result__snippet")
            if not link:
                continue
            href = _clean_duckduckgo_url(link.get("href", ""))
            results.append(
                {
                    "title": link.get_text(" ", strip=True),
                    "url": href,
                    "snippet": snippet.get_text(" ", strip=True) if snippet else "",
                }
            )
            if len(results) >= max_results:
                break

        if not results:
            return ToolResult(tool="web_search", ok=False, content="No search results found.")

        content = "\n".join(
            f"{idx + 1}. {item['title']} - {item['url']}\n   {item['snippet']}"
            for idx, item in enumerate(results)
        )
        return ToolResult(tool="web_search", ok=True, content=content, data={"results": results})

    def control_browser(action: Any) -> ToolResult:
        parsed = _parse_browser_action(action)
        kind = parsed.get("type", "open_url")

        if kind == "search":
            query = str(parsed.get("query", "")).strip()
            if not query:
                return ToolResult(tool="control_browser", ok=False, content="Search query is empty.")
            url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
        elif kind == "open_url":
            url = str(parsed.get("url", "")).strip()
            if not url:
                return ToolResult(tool="control_browser", ok=False, content="URL is empty.")
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
        else:
            return ToolResult(
                tool="control_browser",
                ok=False,
                content=f"Unsupported browser action: {kind}. Supported: open_url, search.",
            )

        webbrowser.open(url)
        return ToolResult(tool="control_browser", ok=True, content=f"Opened browser: {url}", data={"url": url})

    return [
        ToolSpec(
            name="web_search",
            description="Search the web using DuckDuckGo HTML results.",
            parameters={"query": "string", "max_results": "optional integer"},
            handler=web_search,
        ),
        ToolSpec(
            name="control_browser",
            description="Open a URL or search query in the default browser.",
            parameters={"action": "object or string"},
            handler=control_browser,
        ),
    ]


def _parse_browser_action(action: Any) -> dict[str, Any]:
    if isinstance(action, dict):
        return action
    if isinstance(action, str):
        text = action.strip()
        if text.startswith("{"):
            return json.loads(text)
        if text.startswith(("http://", "https://")) or "." in text.split(" ")[0]:
            return {"type": "open_url", "url": text}
        return {"type": "search", "query": text}
    return {}


def _clean_duckduckgo_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if "uddg" in query:
        return query["uddg"][0]
    return url
