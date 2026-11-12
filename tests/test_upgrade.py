"""v0.2 checks for safety, persistence and user-facing library tools."""
import csv
import hashlib
import importlib
import io
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from bookharbor.storage import Store
from bookharbor import downloads


def book(title='Library Book'):
    return {'source': 'gutenberg', 'id': '512', 'title': title,
            'author': 'Writer', 'year': '', 'page': '', 'access': '',
            'formats': {'epub': 'https://www.gutenberg.org/ebooks/512.epub'}}


def test_legacy_database_migration(tmp_path):
    db_path = tmp_path / 'data.db'
    with sqlite3.connect(db_path) as conn:
        conn.execute('CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT,source TEXT NOT NULL, book_id TEXT NOT NULL, title TEXT NOT NULL,author TEXT NOT NULL,format TEXT NOT NULL,url TEXT NOT NULL,status TEXT NOT NULL DEFAULT "queued",path TEXT DEFAULT "",byte_count INTEGER DEFAULT 0,error TEXT DEFAULT "",created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        conn.execute("INSERT INTO jobs(source,book_id,title,author,format,url,status) VALUES('gutenberg','1','Old','A','epub','https://www.gutenberg.org/ebooks/1.epub','running')")
    store = Store(db_path)
    assert store.get(1)['sha256'] == ''
    assert store.get(1)['status'] == 'interrupted'
    assert store.summary()['completed'] == 0


def test_same_book_queue_prevents_duplicate_and_allows_missing_file_redownload(tmp_path):
    store = Store(tmp_path / 'data.db')
    payload = book()
    url = payload['formats']['epub']
    first_id, created, reason = store.add_unique(payload, 'epub', url)
    assert (created, reason) == (True, 'queued')
    assert store.add_unique(payload, 'epub', url) == (first_id, False, 'queued')
    saved = tmp_path / 'real.epub'
    saved.write_bytes(b'content')
    store.update(first_id, 'complete', str(saved), 7, sha256='abc')
    assert store.add_unique(payload, 'epub', url) == (first_id, False, 'complete')
    saved.unlink()
    second_id, created, reason = store.add_unique(payload, 'epub', url)
    assert second_id != first_id and created


def test_concurrent_unique_queue(tmp_path):
    store = Store(tmp_path / 'history.db')
    payload = book()
    with ThreadPoolExecutor(max_workers=8) as pool:
        answers = list(pool.map(lambda _: store.add_unique(payload, 'epub', payload['formats']['epub']), range(14)))
    assert sum(created for _id, created, _status in answers) == 1
    assert len({id for id, _created, _status in answers}) == 1


def test_library_filter_escape_and_summary(tmp_path):
    store = Store(tmp_path / 'history.db')
    j1=store.add(book('Percent% Title'), 'epub', 'https://www.gutenberg.org/ebooks/512.epub')
    store.add(book('Other Name'), 'pdf', 'https://www.gutenberg.org/ebooks/512.pdf')
    assert len(store.list_filtered('%')) == 1
    assert store.list_filtered('not-here') == []
    store.update(j1, 'complete', str(tmp_path / 'book.epub'), 258)
    assert len(store.list_filtered('Percent', 'complete')) == 1
    assert store.summary() == {'completed': 1, 'bytes': 258}


@pytest.fixture
def webapp(monkeypatch, tmp_path):
    monkeypatch.setenv('BOOKHARBOR_HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('BOOKHARBOR_LIBRARY', str(tmp_path / 'books'))
    import app
    return importlib.reload(app)


def test_single_download_is_idempotent(webapp, monkeypatch):
    calls=[]
    monkeypatch.setattr(webapp.download_executor, 'submit', lambda *args, **kwargs: calls.append(args))
    token = webapp.searchable_book(book())['download_options'][0]['token']
    client = TestClient(webapp.app)
    first=client.post('/api/download', json={'token': token})
    second=client.post('/api/download', json={'token': token})
    assert first.status_code == 202 and not first.json()['reused']
    assert second.status_code == 200 and second.json()['reused']
    assert len(calls) == 1


def test_retry_failed_only_and_recheck_archive(webapp, monkeypatch):
    calls=[]
    monkeypatch.setattr(webapp.download_executor, 'submit', lambda *args, **kwargs: calls.append(args))
    client = TestClient(webapp.app)
    url = 'https://www.gutenberg.org/ebooks/512.epub'
    j=webapp.store.add(book(), 'epub', url)
    assert client.post(f'/api/retry/{j}').status_code == 403
    assert client.post(f'/api/retry/{j}', headers={'X-BookHarbor-Action': 'retry'}).status_code == 409
    webapp.store.update(j, 'failed', error='transient')
    resp=client.post(f'/api/retry/{j}', headers={'X-BookHarbor-Action': 'retry'})
    assert resp.status_code == 202 and resp.json()['job_id'] != j
    assert len(calls) == 1
    archive_book = {**book(), 'source': 'archive', 'id': 'archive_1'}
    archive_url = 'https://archive.org/download/archive_1/f.pdf'
    k=webapp.store.add(archive_book, 'pdf', archive_url)
    webapp.store.update(k, 'failed')
    monkeypatch.setattr(webapp, 'archive_formats', lambda _: {})
    assert client.post(f'/api/retry/{k}', headers={'X-BookHarbor-Action': 'retry'}).status_code == 400
    assert len(calls) == 1


def test_file_verify_and_csv_sanitization(webapp):
    client=TestClient(webapp.app)
    p=webapp.LIBRARY / 'real.pdf'
    p.write_bytes(b'%PDF-abc'*100)
    b=book('=SUM(1,1)')
    j=webapp.store.add(b, 'pdf', 'https://www.gutenberg.org/ebooks/512.pdf')
    digest=hashlib.sha256(p.read_bytes()).hexdigest()
    webapp.store.update(j, 'complete', str(p), p.stat().st_size, sha256=digest)
    assert client.get(f'/api/verify/{j}').json()['status'] == 'verified'
    p.write_bytes(b'%PDF-corrupt')
    assert client.get(f'/api/verify/{j}').json()['status'] == 'mismatch'
    p.unlink()
    assert client.get(f'/api/verify/{j}').json()['status'] == 'missing'
    r=client.get('/library/export.csv')
    assert r.status_code == 200 and 'text/csv' in r.headers['content-type']
    rows=list(csv.DictReader(io.StringIO(r.text)))
    assert rows[0]['title'] == "'=SUM(1,1)"
    assert digest == rows[0]['sha256']


def test_old_completed_file_reports_untracked(webapp):
    client=TestClient(webapp.app)
    path=webapp.LIBRARY/'legacy.epub'
    path.write_bytes(b'PK' + b'abc'*70)
    j=webapp.store.add(book(), 'epub', book()['formats']['epub'])
    webapp.store.update(j, 'complete', str(path), path.stat().st_size)
    assert client.get(f'/api/verify/{j}').json()['status'] == 'untracked'


def test_prevent_filename_collisions(webapp, monkeypatch, tmp_path):
    class FakeResponse:
        def __init__(self):
            self.headers = {'Content-Length': '1000', 'Content-Type': 'application/pdf'}
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def iter_content(self, **kwargs): yield b'%PDF-1.4 ' + (b'file' * 300)
    monkeypatch.setattr(downloads, 'safe_get', lambda *args: FakeResponse())
    first=webapp.store.add(book('Same Title'), 'pdf', 'https://www.gutenberg.org/ebooks/512.pdf')
    second=webapp.store.add(book('Same Title'), 'pdf', 'https://www.gutenberg.org/ebooks/512.pdf')
    downloads.run_download(webapp.store, webapp.LIBRARY, first)
    downloads.run_download(webapp.store, webapp.LIBRARY, second)
    a,b=webapp.store.get(first),webapp.store.get(second)
    assert a['status'] == 'complete' and b['status'] == 'complete'
    assert a['path'] != b['path']
    assert Path(a['path']).is_file() and Path(b['path']).is_file()
