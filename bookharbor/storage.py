"""Tiny SQLite ledger; each thread gets its own transaction/connection."""
from __future__ import annotations
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 source TEXT NOT NULL, book_id TEXT NOT NULL, title TEXT NOT NULL,
 author TEXT NOT NULL, format TEXT NOT NULL, url TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued', path TEXT DEFAULT '',
 byte_count INTEGER DEFAULT 0, error TEXT DEFAULT '',
 created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs(status);
"""

class Store:
    def __init__(self, db_file: Path):
        self.path = Path(db_file)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
            # Restart safety: an interrupted process leaves unfinished jobs.
            db.execute("UPDATE jobs SET status='interrupted', error='App stopped before job finished' WHERE status IN ('queued','running')")

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def add(self, book: dict, fmt: str, url: str) -> int:
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO jobs(source,book_id,title,author,format,url) VALUES(?,?,?,?,?,?)",
                (book["source"], book["id"], book["title"][:500], book["author"][:300], fmt, url))
            return int(cursor.lastrowid)

    def update(self, job_id: int, status: str, path: str = "", byte_count: int = 0, error: str = ""):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status=?, path=?, byte_count=?, error=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                       (status, path, byte_count, error[:700], job_id))

    def list(self, limit: int = 100) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,))]

    def get(self, job_id: int) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            return dict(row) if row else None
