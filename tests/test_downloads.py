from pathlib import Path
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
    monkeypatch.setattr(d, 'safe_get', lambda *a, **k: FakeResponse(b'PK' + b'example text '*80))
    d.run_download(store, tmp_path/'books', job)
    result = store.get(job)
    assert result['status'] == 'complete'
    assert Path(result['path']).exists()
    assert result['byte_count'] > 100


def test_download_rejects_markup(monkeypatch, tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    url = 'https://www.gutenberg.org/ebooks/1.epub'
    job = store.add({'source':'gutenberg','id':'1','title':'Fail','author':'Writer'},'epub',url)
    monkeypatch.setattr(d, 'safe_get', lambda *a, **k: FakeResponse(b'<!doctype html><html>not an epub</html>'*10))
    d.run_download(store, tmp_path/'books', job)
    assert store.get(job)['status'] == 'failed'
    assert not list((tmp_path/'books').glob('*.epub'))
