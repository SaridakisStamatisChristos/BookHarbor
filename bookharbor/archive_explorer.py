"""Explicit, cursor-paged Internet Archive metadata exploration and local indexing.

Uses Archive's public scrape endpoint, not HTML scraping. Index entries are *not*
assertions that ebook files are public. Check the item's metadata before downloading.
"""
from __future__ import annotations

import json
import re
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import quote

import requests

from .providers import CatalogError, HEADERS, safe_identifier, MAX_FILE_BYTES

SCRAPE_ENDPOINT = "https://archive.org/services/search/v1/scrape"
FIELDS = "identifier,title,creator,year,date,language,subject,collection,downloads,mediatype"
PAGE_SIZE = 100  # Archive's documented scrape API minimum.
MAX_PER_SESSION = 50000
MIN_REQUEST_SPACING = 1.0
SAFE_WORD = re.compile(r"[^\W_][\w'-]*", re.UNICODE)
VALID_LANGUAGE = re.compile(r"[a-z]{2,3}")
VALID_COLLECTION = re.compile(r"[A-Za-z0-9_.-]{1,100}")


def _text(value, limit: int = 240) -> str:
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(p) for p in value[:5] if p is not None)
    return str(value or "").replace("\x00", "").strip()[:limit]


def _lucene_words(value: str, n: int = 8) -> str:
    # No raw user-supplied Lucene syntax may reach the remote search API.
    return " ".join(SAFE_WORD.findall(value)[:n])


@dataclass(frozen=True)
class ArchiveFilters:
    query: str = ""
    author: str = ""
    subject: str = ""
    language: str = ""
    collection: str = ""
    year_from: int | None = None
    year_to: int | None = None

    @classmethod
    def parse(cls, values: dict) -> "ArchiveFilters":
        if not isinstance(values, dict):
            raise ValueError("Filters must be an object")
        query = _lucene_words(str(values.get("query") or "")[:120])
        author = _lucene_words(str(values.get("author") or "")[:100], 6)
        subject = _lucene_words(str(values.get("subject") or "")[:100], 6)
        language = str(values.get("language") or "").lower().strip()
        collection = str(values.get("collection") or "").strip()
        if language and not VALID_LANGUAGE.fullmatch(language):
            raise ValueError("Language must have a 2- or 3-letter code")
        if collection and not VALID_COLLECTION.fullmatch(collection):
            raise ValueError("Collection must be an Internet Archive collection identifier")
        def year(key):
            raw = values.get(key)
            if raw in ("", None):
                return None
            if isinstance(raw, bool) or not re.fullmatch(r"\d{4}", str(raw)):
                raise ValueError(f"Invalid {key}")
            number = int(raw)
            if number < 1000 or number > 2100:
                raise ValueError(f"Invalid {key}")
            return number
        start, end = year("year_from"), year("year_to")
        if start and end and start > end:
            raise ValueError("Year range is reversed")
        if not (query or author or subject or collection):
            raise ValueError("Enter search terms, an author, a subject or a collection")
        return cls(query, author, subject, language, collection, start, end)

    def expression(self) -> str:
        clauses = ["mediatype:texts"]
        if self.query:
            # Find all query terms within title/creator/subject metadata.
            words = self.query.split()
            quoted = " AND ".join('"' + x.replace('"', '') + '"' for x in words)
            clauses.append("(title:(" + quoted + ") OR creator:(" + quoted + ") OR subject:(" + quoted + "))")
        if self.author:
            quoted = " AND ".join('"' + x + '"' for x in self.author.split())
            clauses.append("creator:(" + quoted + ")")
        if self.subject:
            quoted = " AND ".join('"' + x + '"' for x in self.subject.split())
            clauses.append("subject:(" + quoted + ")")
        if self.language:
            clauses.append(f"language:{self.language}")
        if self.collection:
            clauses.append(f"collection:{self.collection}")
        if self.year_from or self.year_to:
            clauses.append(f"year:[{self.year_from or 1000} TO {self.year_to or 2100}]")
        return " AND ".join(clauses)


def scrape_page(filters: ArchiveFilters, cursor: str | None = None) -> tuple[list[dict], str | None, int | None]:
    """Fetch ONE page of Archive records, respecting the official cursor protocol."""
    params = {"q": filters.expression(), "fields": FIELDS, "count": PAGE_SIZE}
    if cursor:
        if not isinstance(cursor, str) or len(cursor) > 4096:
            raise CatalogError("Invalid cursor")
        params["cursor"] = cursor
    try:
        response = requests.get(SCRAPE_ENDPOINT, params=params, timeout=(12, 45),
                                headers=HEADERS)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise CatalogError(f"Archive scrape unavailable: {str(exc)[:230]}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise CatalogError("Archive supplied an invalid scrape response")
    items = data["items"]
    if any(isinstance(item,dict) and item.get('mediatype') not in (None, 'texts') for item in items):
        raise CatalogError('Archive returned non-text items; possible stale response')
    if len(items) > PAGE_SIZE:
        raise CatalogError("Archive returned more than the requested page size")
    next_cursor = data.get("cursor") or None
    if next_cursor is not None and (not isinstance(next_cursor, str) or len(next_cursor) > 4096):
        raise CatalogError("Archive returned an invalid cursor")
    # Do not infinitely loop if a provider returns a repeated cursor.
    if next_cursor and next_cursor == cursor:
        raise CatalogError("Archive returned the same cursor twice")
    total = data.get("total")
    if not isinstance(total, int) or isinstance(total, bool):
        total = None
    return items, next_cursor, total


def advancedsearch_page(filters: ArchiveFilters, page: int) -> tuple[list[dict], int | None]:
    """Conservative fallback when the upstream scrape cursor is replayed.

    IA caps sorted pagination at 10,000 results; callers MUST mark the limit.
    """
    if not 1 <= page <= 100:
        raise CatalogError('Standard Archive pagination stops at 10,000 results; refine your filters')
    params = {'q':filters.expression(), 'output':'json', 'rows':100, 'page':page,
              'fl[]': FIELDS.split(','), 'sort[]':'identifier asc'}
    try:
        resp = requests.get('https://archive.org/advancedsearch.php',params=params,
                            headers=HEADERS,timeout=(12,45))
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise CatalogError('Archive pagination unavailable: '+str(exc)[:230]) from exc
    if not isinstance(data,dict) or not isinstance(data.get('response'),dict):
        raise CatalogError('Archive returned invalid paginated search results')
    result = data['response']
    rows = result.get('docs')
    if not isinstance(rows,list) or len(rows)>100:
        raise CatalogError('Archive returned an invalid paginated result page')
    total = result.get('numFound')
    if not isinstance(total,int) or isinstance(total,bool):
        total = None
    return rows,total


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions(
 id TEXT PRIMARY KEY, filters_json TEXT NOT NULL, expression TEXT NOT NULL,
 cursor TEXT, page_count INTEGER NOT NULL DEFAULT 0,
 discovered INTEGER NOT NULL DEFAULT 0, estimate INTEGER,
 finished INTEGER NOT NULL DEFAULT 0, last_error TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 mode TEXT NOT NULL DEFAULT 'cursor', fallback_page INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS catalog(
 identifier TEXT PRIMARY KEY, title TEXT NOT NULL, author TEXT NOT NULL,
 year TEXT NOT NULL DEFAULT '', language TEXT NOT NULL DEFAULT '',
 subject TEXT NOT NULL DEFAULT '', collection TEXT NOT NULL DEFAULT '',
 downloads INTEGER NOT NULL DEFAULT 0, access TEXT NOT NULL DEFAULT 'unchecked',
 formats_json TEXT NOT NULL DEFAULT '{}', checked_at TEXT,
 seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS session_items(
 session_id TEXT NOT NULL REFERENCES sessions(id),
 identifier TEXT NOT NULL REFERENCES catalog(identifier),
 ordinal INTEGER NOT NULL,
 PRIMARY KEY(session_id, identifier)
);
CREATE INDEX IF NOT EXISTS session_items_order ON session_items(session_id,ordinal);
CREATE INDEX IF NOT EXISTS catalog_access ON catalog(access);
"""


class ArchiveCatalog:
    def __init__(self, path: Path, *, min_spacing: float = MIN_REQUEST_SPACING):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._last_request = 0.0
        self.min_spacing = min_spacing
        self._harvest_lock = threading.Lock()
        self._harvest_jobs = {}
        with self.connect() as db:
            db.executescript(SCHEMA)
            columns = {row['name'] for row in db.execute('PRAGMA table_info(sessions)')}
            if 'mode' not in columns:
                db.execute("ALTER TABLE sessions ADD COLUMN mode TEXT NOT NULL DEFAULT 'cursor'")
            if 'fallback_page' not in columns:
                db.execute("ALTER TABLE sessions ADD COLUMN fallback_page INTEGER NOT NULL DEFAULT 0")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def start(self, raw: dict) -> dict:
        filters = ArchiveFilters.parse(raw)
        session_id = secrets.token_hex(16)
        with self.connect() as db:
            db.execute('INSERT INTO sessions(id,filters_json,expression) VALUES (?,?,?)',
                       (session_id, json.dumps(asdict(filters)), filters.expression()))
        return self.next_page(session_id)

    def get_session(self, session_id: str) -> dict | None:
        if not re.fullmatch(r'[a-f0-9]{32}', str(session_id)):
            return None
        with self.connect() as db:
            row = db.execute('SELECT * FROM sessions WHERE id=?', (session_id,)).fetchone()
            return dict(row) if row else None

    def next_page(self, session_id: str) -> dict:
        # Serialise page advancement to avoid two calls racing the same cursor.
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                raise ValueError('Unknown exploration session')
            if session['finished']:
                return self._view_session(session)
            if session['discovered'] >= MAX_PER_SESSION:
                with self.connect() as db:
                    db.execute('UPDATE sessions SET finished=1 WHERE id=?', (session_id,))
                return self._view_session(self.get_session(session_id))
            delay = self.min_spacing - (time.monotonic() - self._last_request)
            if delay > 0:
                time.sleep(delay)
            self._last_request = time.monotonic()
            filters = ArchiveFilters(**json.loads(session['filters_json']))
            mode = session['mode']
            fallback_page = session['fallback_page']
            try:
                if mode == 'advanced':
                    fallback_page += 1
                    raw_items, estimate = advancedsearch_page(filters, fallback_page)
                    new_cursor = None
                else:
                    try:
                        raw_items, new_cursor, estimate = scrape_page(filters, session['cursor'])
                    except CatalogError as exc:
                        if session['page_count'] and ('same cursor' in str(exc) or 'repeated' in str(exc)):
                            # Re-read fallback page 1 to avoid skipping records if
                            # the provider's cursor ordering differs from sorted pages.
                            mode = 'advanced'
                            fallback_page = 1
                            raw_items, estimate = advancedsearch_page(filters, fallback_page)
                            new_cursor = None
                        else:
                            raise
            except CatalogError as exc:
                with self.connect() as db:
                    db.execute('UPDATE sessions SET last_error=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
                               (str(exc)[:350], session_id))
                raise
            valid = []
            unique = set()
            for raw in raw_items:
                if not isinstance(raw, dict):
                    continue
                identifier = str(raw.get('identifier') or '')
                if not safe_identifier(identifier) or identifier in unique:
                    continue
                unique.add(identifier)
                valid.append({
                    'identifier': identifier,
                    'title': _text(raw.get('title'), 450) or 'Untitled',
                    'author': _text(raw.get('creator'), 300) or 'Unknown',
                    'year': _text(raw.get('year') or raw.get('date'), 32)[:10],
                    'language': _text(raw.get('language'), 100),
                    'subject': _text(raw.get('subject'), 600),
                    'collection': _text(raw.get('collection'), 250),
                    'downloads': max(0, int(raw.get('downloads') or 0)) if str(raw.get('downloads') or '0').isdigit() else 0,
                })
            # Reject a repeated page (e.g. an upstream stale-cache response).
            # Retain current cursor so a retry can recover without losing state.
            with self.connect() as db:
                known = {r[0] for r in db.execute('SELECT identifier FROM session_items WHERE session_id=?', (session_id,))}
            fresh = [item for item in valid if item['identifier'] not in known]
            if mode == 'cursor' and session['page_count'] and valid and not fresh:
                raise CatalogError('Archive repeated an already indexed page; retry later')
            # One transaction inserts records and advances the cursor atomically.
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                for i, item in enumerate(fresh):
                    db.execute('''INSERT INTO catalog(identifier,title,author,year,language,subject,collection,downloads)
                         VALUES(:identifier,:title,:author,:year,:language,:subject,:collection,:downloads)
                         ON CONFLICT(identifier) DO UPDATE SET
                         title=excluded.title,author=excluded.author,year=excluded.year,
                         language=excluded.language,subject=excluded.subject,
                         collection=excluded.collection,downloads=excluded.downloads,
                         seen_at=CURRENT_TIMESTAMP''', item)
                    db.execute('INSERT OR IGNORE INTO session_items(session_id,identifier,ordinal) VALUES(?,?,?)',
                               (session_id, item['identifier'], session['discovered'] + i))
                stopped = (not raw_items or session['discovered'] + len(fresh) >= MAX_PER_SESSION or
                           (mode == 'cursor' and not new_cursor) or
                           (mode == 'advanced' and (fallback_page >= 100 or
                            (estimate is not None and fallback_page * 100 >= estimate))))
                db.execute('''UPDATE sessions SET cursor=?, page_count=page_count+1, discovered=discovered+?,
                          estimate=COALESCE(estimate,?), finished=?, last_error='', updated_at=CURRENT_TIMESTAMP,
                          mode=?, fallback_page=? WHERE id=?''',
                           (new_cursor if mode=='cursor' and not stopped else None,
                            len(fresh), estimate, int(stopped), mode, fallback_page, session_id))
            return self._view_session(self.get_session(session_id))

    def _view_session(self, row: dict) -> dict:
        return {key: row[key] for key in ('id', 'expression', 'page_count', 'discovered',
                                          'estimate', 'finished', 'last_error', 'created_at', 'updated_at', 'mode', 'fallback_page')}

    def session_status(self, session_id: str) -> dict:
        row = self.get_session(session_id)
        if not row:
            raise ValueError('Unknown exploration session')
        return self._view_session(row)

    def list_items(self, session_id: str, query: str = '', access: str = 'all',
                   offset: int = 0, limit: int = 50) -> dict:
        if not self.get_session(session_id):
            raise ValueError('Unknown exploration session')
        if access not in ('all', 'public', 'unchecked', 'unavailable'):
            raise ValueError('Unknown access filter')
        offset = max(0, min(offset, 100000))
        limit = max(1, min(limit, 100))
        term = '%' + query[:120].replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + '%'
        where = "WHERE s.session_id=?"
        params = [session_id]
        if query:
            where += " AND (c.title LIKE ? ESCAPE '\\' OR c.author LIKE ? ESCAPE '\\' OR c.subject LIKE ? ESCAPE '\\')"
            params.extend([term] * 3)
        if access != 'all':
            where += ' AND c.access=?'
            params.append(access)
        source = ' FROM session_items s JOIN catalog c ON c.identifier=s.identifier ' + where
        with self.connect() as db:
            total = db.execute('SELECT COUNT(*)' + source, params).fetchone()[0]
            rows = db.execute('SELECT c.*,s.ordinal' + source + ' ORDER BY s.ordinal LIMIT ? OFFSET ?',
                              (*params, limit, offset)).fetchall()
        return {'total': total, 'items': [self._as_book(dict(row)) for row in rows],
                'offset': offset, 'limit': limit}

    def _as_book(self, entry: dict) -> dict:
        return {'source': 'archive', 'id': entry['identifier'], 'title': entry['title'],
                'author': entry['author'], 'year': entry['year'],
                'page': 'https://archive.org/details/' + quote(entry['identifier']),
                'access': entry['access'], 'formats': json.loads(entry['formats_json']),
                'language': entry['language'], 'subject': entry['subject'],
                'collection': entry['collection']}

    def record(self, identifier: str) -> dict | None:
        with self.connect() as db:
            row = db.execute('SELECT * FROM catalog WHERE identifier=?', (identifier,)).fetchone()
        return self._as_book(dict(row)) if row else None

    def mark_formats(self, identifier: str, formats: dict[str, str]) -> None:
        if not safe_identifier(identifier):
            raise ValueError('Invalid identifier')
        from .providers import allowed_url
        vetted = {key: url for key, url in formats.items()
                  if key in ('epub','pdf','txt','mobi') and allowed_url(url, 'archive')}
        with self.connect() as db:
            db.execute('''UPDATE catalog SET access=?,formats_json=?,checked_at=CURRENT_TIMESTAMP
                       WHERE identifier=?''',
                       ('public' if vetted else 'unavailable', json.dumps(vetted), identifier))

    def start_harvest(self, session_id: str, pages: int = 10) -> dict:
        """Explicit, bounded background indexing; no unattended recurring crawler."""
        if isinstance(pages, bool) or not isinstance(pages, int) or not 1 <= pages <= 50:
            raise ValueError('Choose 1 to 50 pages (100–5,000 metadata records)')
        state = self.session_status(session_id)
        if state['finished']:
            raise ValueError('This session has finished indexing')
        with self._harvest_lock:
            prior = self._harvest_jobs.get(session_id)
            if prior and prior['thread'].is_alive():
                raise ValueError('An indexing batch is already running for this search')
            stop = threading.Event()
            job = {'thread': None, 'stop': stop, 'pages': pages, 'completed': 0}

            def worker():
                for _ in range(pages):
                    if stop.is_set():
                        break
                    try:
                        page = self.next_page(session_id)
                        job['completed'] += 1
                    except Exception as exc:
                        with self.connect() as db:
                            db.execute('UPDATE sessions SET last_error=? WHERE id=?',
                                       (str(exc)[:350], session_id))
                        break
                    if page['finished']:
                        break

            job['thread'] = threading.Thread(target=worker, daemon=True,
                                           name='archive-harvest-' + session_id[:8])
            self._harvest_jobs[session_id] = job
            job['thread'].start()
        return self.harvest_status(session_id)

    def stop_harvest(self, session_id: str) -> dict:
        if not self.get_session(session_id):
            raise ValueError('Unknown exploration session')
        with self._harvest_lock:
            job = self._harvest_jobs.get(session_id)
            if job and job['thread'].is_alive():
                job['stop'].set()
        return self.harvest_status(session_id)

    def harvest_status(self, session_id: str) -> dict:
        state = self.session_status(session_id)
        with self._harvest_lock:
            job = self._harvest_jobs.get(session_id)
            state['harvesting'] = bool(job and job['thread'].is_alive())
            state['harvest_completed_pages'] = job['completed'] if job else 0
            state['harvest_target_pages'] = job['pages'] if job else 0
            state['stop_requested'] = bool(job and job['stop'].is_set())
        return state

    def stats(self) -> dict:
        with self.connect() as db:
            count, verified = db.execute("SELECT COUNT(*),SUM(access='public') FROM catalog").fetchone()
            sessions = db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]
        return {'indexed': count, 'public_verified': verified or 0, 'sessions': sessions}
