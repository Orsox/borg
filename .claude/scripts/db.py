#!/home/bernd/.claude/venv/bin/python3
"""DB abstraction: SQLite + sqlite-vec (local) or Postgres + pgvector (VPS).

Detects backend from DB_URL env var:
  - unset / empty       → SQLite at ~/.claude/data/memory.db
  - postgresql://...    → Postgres with pgvector (Phase 9)

Public API:
  get_db()                                  → DB instance
  db.upsert_chunks(path, chunks, embeddings, mtime)
  db.delete_chunks_for_path(path)
  db.vector_search(embedding, k, path_prefix) → list[dict]
  db.keyword_search(query, k, path_prefix)    → list[dict]
  db.get_indexed_mtimes()                     → dict[path, mtime]
"""
import os
import struct
import pathlib
import sqlite3
import sqlite_vec

DB_PATH = pathlib.Path.home() / ".claude" / "data" / "memory.db"


def _serialize(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


class SQLiteDB:
    def __init__(self, db_path: pathlib.Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.enable_load_extension(True)
        sqlite_vec.load(self._conn)
        self._conn.enable_load_extension(False)
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS chunks (
                rowid   INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id TEXT UNIQUE NOT NULL,
                path     TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content  TEXT NOT NULL,
                mtime    REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);

            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
                embedding float[384]
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                chunk_id UNINDEXED,
                content,
                tokenize = 'porter ascii'
            );
        """)
        self._conn.commit()

    def upsert_chunks(
        self,
        path: str,
        chunks: list[str],
        embeddings: list[list[float]],
        mtime: float,
    ):
        """Replace all chunks for a path with new ones."""
        self.delete_chunks_for_path(path)
        for i, (content, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_id = f"{path}::{i}"
            cursor = self._conn.execute(
                "INSERT INTO chunks (chunk_id, path, chunk_index, content, mtime)"
                " VALUES (?, ?, ?, ?, ?)",
                [chunk_id, path, i, content, mtime],
            )
            rowid = cursor.lastrowid
            self._conn.execute(
                "INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
                [rowid, _serialize(embedding)],
            )
            self._conn.execute(
                "INSERT INTO chunks_fts (rowid, chunk_id, content) VALUES (?, ?, ?)",
                [rowid, chunk_id, content],
            )
        self._conn.commit()

    def delete_chunks_for_path(self, path: str):
        rowids = [
            r[0]
            for r in self._conn.execute(
                "SELECT rowid FROM chunks WHERE path = ?", [path]
            ).fetchall()
        ]
        for rowid in rowids:
            self._conn.execute("DELETE FROM chunks_vec WHERE rowid = ?", [rowid])
            self._conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", [rowid])
        self._conn.execute("DELETE FROM chunks WHERE path = ?", [path])
        self._conn.commit()

    def vector_search(
        self,
        embedding: list[float],
        k: int = 10,
        path_prefix: str | None = None,
    ) -> list[dict]:
        blob = _serialize(embedding)
        rows = self._conn.execute(
            """
            SELECT c.chunk_id, c.path, c.content, v.distance
            FROM chunks_vec v
            JOIN chunks c ON c.rowid = v.rowid
            WHERE v.embedding MATCH ?
              AND k = ?
            ORDER BY v.distance
            """,
            [blob, k * 3],  # fetch extra, filter after
        ).fetchall()
        results = []
        for r in rows:
            if path_prefix and not r["path"].startswith(path_prefix):
                continue
            results.append(
                {"chunk_id": r["chunk_id"], "path": r["path"],
                 "content": r["content"], "score": float(r["distance"])}
            )
            if len(results) >= k:
                break
        return results

    def keyword_search(
        self,
        query: str,
        k: int = 10,
        path_prefix: str | None = None,
    ) -> list[dict]:
        try:
            rows = self._conn.execute(
                """
                SELECT f.chunk_id, c.path, c.content, f.rank
                FROM chunks_fts f
                JOIN chunks c ON c.rowid = f.rowid
                WHERE chunks_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                [query, k * 3 if path_prefix else k],
            ).fetchall()
        except sqlite3.OperationalError:
            return []  # invalid FTS query syntax — return empty
        results = []
        for r in rows:
            if path_prefix and not r["path"].startswith(path_prefix):
                continue
            # FTS5 rank is negative (lower = better match), invert for score
            results.append(
                {"chunk_id": r["chunk_id"], "path": r["path"],
                 "content": r["content"], "score": -float(r["rank"])}
            )
            if len(results) >= k:
                break
        return results

    def get_indexed_mtimes(self) -> dict[str, float]:
        rows = self._conn.execute(
            "SELECT path, MAX(mtime) as mtime FROM chunks GROUP BY path"
        ).fetchall()
        return {r["path"]: r["mtime"] for r in rows}

    def get_all_indexed_paths(self) -> set[str]:
        rows = self._conn.execute("SELECT DISTINCT path FROM chunks").fetchall()
        return {r["path"] for r in rows}


def get_db() -> SQLiteDB:
    db_url = os.environ.get("DB_URL", "")
    if db_url.startswith("postgresql://"):
        raise NotImplementedError("Postgres backend — implement in Phase 9")
    return SQLiteDB()
