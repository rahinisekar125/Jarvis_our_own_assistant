from __future__ import annotations

import re


HINGLISH_KEYWORDS = {
    "aaj",
    "abhi",
    "aur",
    "bajao",
    "bata",
    "batao",
    "chalao",
    "dhoondo",
    "dhundo",
    "hai",
    "karo",
    "khol",
    "kholo",
    "kholna",
    "kitna",
    "kya",
    "likh",
    "likho",
    "samay",
}

DEVANAGARI_RE = re.compile(r"[\u0900-\u097f]")


def prefers_hinglish(text: str) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False
    if DEVANAGARI_RE.search(text):
        return True
    tokens = set(normalized.split())
    if tokens & HINGLISH_KEYWORDS:
        return True
    return any(
        phrase in normalized
        for phrase in (
            "open karo",
            "type karo",
            "search karo",
            "google karo",
            "battery status batao",
            "time kya hai",
            "date kya hai",
        )
    )


def style_hint(text: str) -> str:
    if prefers_hinglish(text):
        return "hinglish"
    return "english"


def _normalize(text: str) -> str:
    return " ".join(
        "".join(char.lower() if char.isalnum() or char.isspace() else " " for char in text).split()
    )
