"""SQLite-backed conversation session store.

Each Teams thread (conversation_id) has its own persistent message history.
History survives server restarts.
"""
import datetime
import json
import pathlib
import sqlite3
import threading

DB_PATH = pathlib.Path.home() / ".claude" / "data" / "chat.db"
MAX_HISTORY = 20  # keep last N messages per session to stay within context limits


class SessionStore:
    def __init__(self, db_path: pathlib.Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                conversation_id TEXT PRIMARY KEY,
                platform        TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL,
                history         TEXT NOT NULL DEFAULT '[]'
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_platform ON sessions(platform);
            CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at);
        """)
        self._conn.commit()

    def get_history(self, conversation_id: str) -> list[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT history FROM sessions WHERE conversation_id = ?",
                [conversation_id],
            ).fetchone()
        if not row:
            return []
        return json.loads(row["history"])

    def add_message(self, conversation_id: str, platform: str, role: str, content: str):
        with self._lock:
            history = self.get_history(conversation_id)
            history.append({"role": role, "content": content})
            if len(history) > MAX_HISTORY:
                history = history[-MAX_HISTORY:]

            now = datetime.datetime.now().isoformat()
            self._conn.execute(
                """
                INSERT INTO sessions (conversation_id, platform, created_at, updated_at, history)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    history    = excluded.history
                """,
                [conversation_id, platform, now, now, json.dumps(history)],
            )
            self._conn.commit()

    def clear_session(self, conversation_id: str):
        with self._lock:
            self._conn.execute(
                "DELETE FROM sessions WHERE conversation_id = ?",
                [conversation_id],
            )
            self._conn.commit()

    def list_sessions(self, platform: str | None = None) -> list[dict]:
        with self._lock:
            if platform:
                rows = self._conn.execute(
                    "SELECT conversation_id, platform, created_at, updated_at FROM sessions WHERE platform = ? ORDER BY updated_at DESC",
                    [platform],
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT conversation_id, platform, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
                ).fetchall()
        return [dict(r) for r in rows]
