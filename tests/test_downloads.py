from pathlib import Path
from io import BytesIO
from zipfile import ZipFile
import requests
from bookharbor import downloads as d
from bookharbor.storage import Store


class FakeResponse:
    def __init__(self, data, content_type='application/epub+zip'):
        self.data = data
        self.headers = {'Content-Length': str(len(data)), 'Content-Type': content_type}
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def iter_content(self, chunk_size=100):
        yield self.data


def test_download_success(monkeypatch, tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    url = 'https://www.gutenberg.org/ebooks/1.epub'
    job = store.add({'source':'gutenberg','id':'1','title':'Demo / Safe','author':'Writer'},'epub',url)
    buf = BytesIO()
    with ZipFile(buf, 'w') as zip_out:
        zip_out.writestr('mimetype', 'application/epub+zip')
        zip_out.writestr('OPS/story.xhtml', '<html><body>' + 'Sample book '*100 + '</body></html>')
    data = buf.getvalue()
    monkeypatch.setattr(d, 'safe_get', lambda *a, **k: FakeResponse(data))
    d.run_download(store, tmp_path/'books', job)
    result = store.get(job)
    assert result['status'] == 'complete'
    assert Path(result['path']).exists()
    assert result['byte_count'] > 100
    import hashlib
    assert result['sha256'] == hashlib.sha256(data).hexdigest()


def test_download_rejects_markup(monkeypatch, tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    url = 'https://www.gutenberg.org/ebooks/1.epub'
    job = store.add({'source':'gutenberg','id':'1','title':'Fail','author':'Writer'},'epub',url)
    monkeypatch.setattr(d, 'safe_get', lambda *a, **k: FakeResponse(b'<!doctype html><html>not an epub</html>'*10))
    d.run_download(store, tmp_path/'books', job)
    assert store.get(job)['status'] == 'failed'
    assert not list((tmp_path/'books').glob('*.epub'))


def test_epub_rejects_fake_zip_header(monkeypatch, tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    book = {'source': 'gutenberg', 'id': '2', 'title': 'Fake EPUB', 'author': 'A'}
    job = store.add(book, 'epub', 'https://www.gutenberg.org/fake.epub')
    monkeypatch.setattr(d, 'safe_get', lambda *a, **k: FakeResponse(b'PK' + b'no zip here'*50))
    d.run_download(store, tmp_path/'books', job)
    assert store.get(job)['status'] == 'failed'


def test_partial_read_failure_retries_from_start(monkeypatch, tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    book = {'source': 'archive', 'id': 'example', 'title': 'Essay', 'author': 'A'}
    job = store.add(book, 'txt', 'https://archive.org/download/example/essay.txt')
    calls = [0]
    class Response(FakeResponse):
        def iter_content(self, chunk_size=1024):
            yield b'partial garbage'
            if calls[0] == 1:
                raise requests.exceptions.ConnectionError('temporary socket reset')
            yield b'Good book content '*50
    def flaky(*args, **kwargs):
        calls[0] += 1
        return Response(b'')
    monkeypatch.setattr(d, 'safe_get', flaky)
    monkeypatch.setattr(d.time, 'sleep', lambda n: None)
    d.run_download(store, tmp_path/'books', job)
    result = store.get(job)
    assert calls[0] == 2
    assert result['status'] == 'complete'
    assert Path(result['path']).read_bytes() == b'partial garbage' + b'Good book content '*50


def test_access_denied_not_retried(monkeypatch, tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    job = store.add({'source':'oapen','id':'x','title':'T','author':'A'}, 'txt',
                    'https://library.oapen.org/x.txt')
    n=[0]
    def forbidden(*args, **kwargs):
        n[0]+=1
        response = requests.Response()
        response.status_code=403
        raise requests.exceptions.HTTPError('403 Forbidden', response=response)
    monkeypatch.setattr(d, 'safe_get', forbidden)
    d.run_download(store, tmp_path/'books', job)
    assert n[0] == 1
    assert store.get(job)['status']=='failed'


def test_archive_retry_uses_only_approved_mirror(monkeypatch, tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    url = 'https://archive.org/download/book/book.pdf'
    book = {'source': 'archive', 'id': 'book', 'title': 'Book', 'author': 'A'}
    job = store.add(book, 'pdf', url)
    calls = []
    alt = 'https://ia600308.us.archive.org/12/items/book/book.pdf'
    monkeypatch.setattr(d, 'archive_mirror_urls', lambda ident, canonical: [alt])
    monkeypatch.setattr(d.time, 'sleep', lambda n: None)
    def patched_safe_get(url, source):
        calls.append(url)
        if len(calls) <= 2:
            raise requests.exceptions.Timeout('transient Archive CDN timeout')
        return FakeResponse(b'%PDF-1.7\n' + b'PDF data ' * 90, 'application/pdf')
    monkeypatch.setattr(d, 'safe_get', patched_safe_get)
    d.run_download(store, tmp_path / 'books', job)
    assert calls == [url, url, alt]
    result = store.get(job)
    assert result['status'] == 'complete'
    assert Path(result['path']).read_bytes().startswith(b'%PDF-')
