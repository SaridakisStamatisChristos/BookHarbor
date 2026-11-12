"""SQLite download ledger with v0.1 migration, duplicate-safe queueing, and filters."""
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
CREATE INDEX IF NOT EXISTS jobs_book_idx ON jobs(source,book_id,format,status);
"""


def _escape_like(value: str) -> str:
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


class Store:
    def __init__(self, db_file: Path):
        self.path = Path(db_file)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
            columns = {row['name'] for row in db.execute('PRAGMA table_info(jobs)')}
            if 'sha256' not in columns:
                db.execute("ALTER TABLE jobs ADD COLUMN sha256 TEXT DEFAULT ''")
            # Startup cannot safely presume unfinished jobs were successful.
            db.execute("UPDATE jobs SET status='interrupted', error='App stopped before job finished' WHERE status IN ('queued','running')")

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def add(self, book: dict, fmt: str, url: str) -> int:
        """Legacy low-level insert, useful for jobs created by older code/tests."""
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO jobs(source,book_id,title,author,format,url) VALUES(?,?,?,?,?,?)",
                (book['source'], str(book['id']), str(book['title'])[:500], str(book['author'])[:300], fmt, url))
            return int(cursor.lastrowid)

    def add_unique(self, book: dict, fmt: str, url: str) -> tuple[int, bool, str]:
        """Transactionally reuse queued/running jobs or completed files of the same edition.

        A prior complete row whose file has been deleted does not block recovery.
        The write lock prevents simultaneous API calls from queuing the same edition.
        Returns (job_id, created, reason).
        """
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            matches = db.execute(
                "SELECT id,status,path FROM jobs WHERE source=? AND book_id=? AND format=? "
                "AND status IN ('queued','running','complete') ORDER BY id DESC",
                (book['source'], str(book['id']), fmt)).fetchall()
            for entry in matches:
                if entry['status'] in ('queued', 'running'):
                    return int(entry['id']), False, entry['status']
                if entry['path'] and Path(entry['path']).is_file():
                    return int(entry['id']), False, 'complete'
            cursor = db.execute(
                "INSERT INTO jobs(source,book_id,title,author,format,url) VALUES(?,?,?,?,?,?)",
                (book['source'], str(book['id']), str(book['title'])[:500], str(book['author'])[:300], fmt, url))
            return int(cursor.lastrowid), True, 'queued'

    def update(self, job_id: int, status: str, path: str = '', byte_count: int = 0,
               error: str = '', sha256: str | None = None):
        with self.connect() as db:
            db.execute(
                "UPDATE jobs SET status=?, path=?, byte_count=?, error=?, "
                "sha256=COALESCE(?,sha256), updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, path, byte_count, error[:700], sha256, job_id))

    def list(self, limit: int = 100) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM jobs ORDER BY id DESC LIMIT ?', (limit,))]

    def list_filtered(self, query: str = '', status: str = 'all', limit: int = 200) -> list[dict]:
        where, params = [], []
        if query:
            where.append("(title LIKE ? ESCAPE '\\' OR author LIKE ? ESCAPE '\\' OR source LIKE ? ESCAPE '\\')")
            term = '%' + _escape_like(query) + '%'
            params.extend([term] * 3)
        if status != 'all':
            where.append('status=?')
            params.append(status)
        sql = 'SELECT * FROM jobs' + (' WHERE ' + ' AND '.join(where) if where else '') + ' ORDER BY id DESC LIMIT ?'
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, (*params, limit))]

    def summary(self) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT COUNT(*) AS completed, COALESCE(SUM(byte_count),0) AS bytes "
                             "FROM jobs WHERE status='complete'").fetchone()
            return dict(row)

    def get(self, job_id: int) -> dict | None:
        with self.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            return dict(row) if row else None
