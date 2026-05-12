from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any


class MemoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def remember(self, kind: str, key: str, value: str, importance: int = 1) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO memories(kind, key, value, importance, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(kind, key) DO UPDATE SET
                    value=excluded.value,
                    importance=excluded.importance,
                    updated_at=excluded.updated_at
                """,
                (kind, key, value, importance, _now()),
            )

    def log_event(self, role: str, content: str) -> None:
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO events(ts, role, content) VALUES (?, ?, ?)",
                (_now(), role, content),
            )

    def log_command(
        self,
        user_text: str,
        tool_name: str,
        arguments: dict[str, Any],
        status: str,
        summary: str,
    ) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO commands(ts, user_text, tool_name, arguments, status, summary)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (_now(), user_text, tool_name, json.dumps(arguments), status, summary[:1000]),
            )

    def recent_events(self, limit: int = 12) -> list[dict[str, str]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT ts, role, content FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"ts": row["ts"], "role": row["role"], "content": row["content"]}
            for row in reversed(rows)
        ]

    def memory_summary(self, limit: int = 20) -> str:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT kind, key, value, importance, updated_at
                FROM memories
                ORDER BY importance DESC, updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        if not rows:
            return ""
        return "\n".join(
            f"- [{row['kind']}] {row['key']}: {row['value']}" for row in rows
        )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    importance INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL,
                    UNIQUE(kind, key)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS commands(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    user_text TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    arguments TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL
                )
                """
            )


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
