from fastapi.testclient import TestClient
import importlib
import pytest

@pytest.fixture
def webapp(monkeypatch, tmp_path):
    monkeypatch.setenv("BOOKHARBOR_HOME", str(tmp_path/"home"))
    monkeypatch.setenv("BOOKHARBOR_LIBRARY", str(tmp_path/"books"))
    import app
    return importlib.reload(app)
from bookharbor import archive_explorer as exp


def test_archive_endpoint_lifecycle(webapp,monkeypatch):
    pages=iter([([{'identifier':'public_book','title':'Mathematics','creator':'A Author','language':'en'}], 'next',100),
                ([{'identifier':'book_2','title':'Astronomy'}], None,100)])
    monkeypatch.setattr(exp,'scrape_page',lambda *_:next(pages))
    client=TestClient(webapp.app)
    assert client.get('/archive').status_code==200
    assert 'Explore the Archive' in client.get('/archive').text
    assert client.post('/api/archive/start',json={'query':'math'}).status_code==403
    header={'X-BookHarbor-Action':'archive-explorer'}
    start=client.post('/api/archive/start',json={'query':'math'},headers=header)
    assert start.status_code==200,start.text
    sid=start.json()['id']
    first=client.get('/api/archive/items',params={'session':sid}).json()
    assert first['total']==1
    assert first['items'][0]['inspect_token']
    assert first['items'][0]['availability']=='unchecked'
    assert not first['items'][0]['download_options']
    monkeypatch.setattr(webapp,'archive_formats',lambda _: {'txt':'https://archive.org/download/public_book/book.txt'})
    checked=client.post('/api/archive/inspect',json={'id':'public_book'},headers=header)
    assert checked.status_code==200
    assert checked.json()['availability']=='public'
    assert checked.json()['options'][0]['fmt']=='TXT'
    page2=client.post('/api/archive/next',json={'session':sid},headers=header)
    assert page2.status_code==200 and page2.json()['discovered']==2
    assert client.get('/api/archive/items',params={'session':sid,'access':'public'}).json()['total']==1


def test_explorer_rejects_invalid_batch_and_nonindexed_ids(webapp):
    client=TestClient(webapp.app)
    h={'X-BookHarbor-Action':'archive-explorer'}
    assert client.post('/api/archive/inspect',json={'id':'not_indexed'},headers=h).status_code==404
    assert client.post('/api/archive/verify-selected',json={'ids':['a']*6},headers=h).status_code==400
    assert client.post('/api/archive/harvest',json={'session':'invalid','pages':100},headers=h).status_code==400
