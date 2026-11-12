import importlib
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def webapp(monkeypatch, tmp_path):
    monkeypatch.setenv('BOOKHARBOR_HOME', str(tmp_path/'home'))
    monkeypatch.setenv('BOOKHARBOR_LIBRARY', str(tmp_path/'library'))
    import app
    app = importlib.reload(app)
    return app


def sample_book():
    return {'source':'gutenberg','id':'1342','title':'Pride and Prejudice',
     'author':'Jane Austen','year':'1813',
     'page':'https://www.gutenberg.org/ebooks/1342',
     'access':'Public download', 'formats':{'epub':'https://www.gutenberg.org/ebooks/1342.epub3.images'}}


def test_home_and_search(webapp, monkeypatch):
    monkeypatch.setitem(webapp.SOURCES, 'gutenberg', lambda q, lang: [sample_book()])
    client = TestClient(webapp.app)
    response = client.get('/?q=pride&source=gutenberg')
    assert response.status_code == 200
    assert 'Pride and Prejudice' in response.text
    assert 'Download selected' in response.text
    assert client.get('/library').status_code == 200


def test_signed_download_and_batch(webapp, monkeypatch):
    calls=[]
    monkeypatch.setattr(webapp.download_executor, 'submit', lambda *args, **kwargs: calls.append(args))
    client = TestClient(webapp.app)
    book = sample_book()
    signed = webapp.searchable_book(book)
    option = signed['download_options'][0]
    response = client.post('/api/download', json={'token':option['token']})
    assert response.status_code == 202
    bad = client.post('/api/download', json={'token':'badtoken'})
    assert bad.status_code == 400
    batch = client.post('/api/batch', json={'tokens':[signed['selection_token']], 'preference':'auto'})
    assert batch.status_code == 202
    assert len(batch.json()['queued']) == 1
    assert len(calls) == 2
    assert len(client.get('/api/jobs').json()['jobs']) == 2


def test_archive_never_queues_borrow_only(webapp, monkeypatch):
    monkeypatch.setattr(webapp, 'archive_formats', lambda _identifier: {})
    client = TestClient(webapp.app)
    book = sample_book(); book.update(source='archive', id='restricted_123', formats={})
    token = webapp.searchable_book(book)['inspect_token']
    assert client.get('/api/formats', params={'token': token}).json()['options'] == []
    injected = webapp.mint_token({'source':'archive','id':'restricted_123', 'title':'T',
                                  'author':'A','fmt':'pdf','url':'https://archive.org/download/restricted_123/file.pdf'})
    resp = client.post('/api/download', json={'token': injected})
    assert resp.status_code == 400
