import hashlib
from pathlib import Path
import pytest
import requests
from bookharbor import downloads as d
from bookharbor.storage import Store


class Response:
    def __init__(self, payload, *, status=200, headers=None, interrupt=False):
        self.payload=payload
        self.status_code=status
        self.headers=headers or {'Content-Type':'text/plain','Content-Length':str(len(payload))}
        self.interrupt=interrupt
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def iter_content(self, chunk_size=1234):
        yield self.payload
        if self.interrupt:
            raise requests.exceptions.ConnectionError('connection reset')


def setup(tmp_path):
    store=Store(tmp_path/'history.sqlite')
    job=store.add({'source':'archive','id':'id123','title':'Example','author':'Someone'},
                  'txt','https://archive.org/download/id123/sample.txt')
    return store,job,tmp_path/'books'


def test_resume_after_interrupted_transfer_in_same_job(tmp_path,monkeypatch):
    store,job,root=setup(tmp_path)
    body=b'Public-domain text ' * 140
    head=body[:550]
    responses=[Response(head,status=200,headers={'Content-Type':'text/plain','ETag':'"stable-123"'},interrupt=True),
               Response(body[550:],status=206,headers={'Content-Range':f'bytes 550-{len(body)-1}/{len(body)}',
                   'Content-Length':str(len(body)-550),'ETag':'"stable-123"','Content-Type':'text/plain'})]
    seen=[]
    def get(url,source,**kwargs):
        seen.append(kwargs.get('extra_headers'))
        return responses.pop(0)
    monkeypatch.setattr(d,'safe_get',get)
    monkeypatch.setattr(d.time,'sleep',lambda _:None)
    d.run_download(store,root,job)
    result=store.get(job)
    assert result['status']=='complete',result['error']
    assert Path(result['path']).read_bytes()==body
    assert result['sha256']==hashlib.sha256(body).hexdigest()
    assert seen==[None,{'Range':'bytes=550-','If-Range':'"stable-123"'}]
    assert not list(root.glob('.partial-*.part'))


def test_range_ignored_restarts_without_concatenation(tmp_path,monkeypatch):
    store,job,root=setup(tmp_path)
    body=b'Complete TXT ' * 200
    first=body[:600]
    calls=[]
    def get(url,source,**kwargs):
        calls.append(kwargs.get('extra_headers'))
        if len(calls)==1:return Response(first,headers={'ETag':'"v1"'},interrupt=True)
        return Response(body,headers={'ETag':'"v2"','Content-Length':str(len(body))})
    monkeypatch.setattr(d,'safe_get',get)
    monkeypatch.setattr(d.time,'sleep',lambda _:None)
    d.run_download(store,root,job)
    assert Path(store.get(job)['path']).read_bytes()==body


def test_mismatched_range_never_publishes_corrupt_file(tmp_path,monkeypatch):
    store,job,root=setup(tmp_path)
    calls=[]
    def get(url,source,**kwargs):
        calls.append(1)
        if len(calls)==1:return Response(b'Intro'*120,headers={'ETag':'"v1"'},interrupt=True)
        return Response(b'rest'*140,status=206,
                        headers={'Content-Range':'bytes 20-579/1000', 'ETag':'"v1"'})
    monkeypatch.setattr(d,'safe_get',get)
    monkeypatch.setattr(d.time,'sleep',lambda _:None)
    d.run_download(store,root,job)
    assert store.get(job)['status']=='failed'
    assert not list(root.glob('*.txt'))
    assert not list(root.glob('.partial-*.part'))


def test_partial_persists_for_retry_in_next_job(tmp_path,monkeypatch):
    store,job,root=setup(tmp_path)
    body=b'Scientific text '*200
    first=body[:700]
    def broken(url,source,**kwargs):return Response(first,headers={'ETag':'"v5"'},interrupt=True)
    monkeypatch.setattr(d,'safe_get',broken)
    monkeypatch.setattr(d.time,'sleep',lambda _:None)
    d.run_download(store,root,job)
    assert store.get(job)['status']=='failed'
    assert len(list(root.glob('.partial-*.part')))==1
    new=store.add({'source':'archive','id':'id123','title':'Example','author':'Someone'},
                  'txt','https://archive.org/download/id123/sample.txt')
    def recover(url,source,**kwargs):
        assert kwargs['extra_headers']['Range']=='bytes=700-'
        return Response(body[700:],status=206,headers={'Content-Range':f'bytes 700-{len(body)-1}/{len(body)}',
                          'Content-Length':str(len(body)-700),'ETag':'"v5"'})
    monkeypatch.setattr(d,'safe_get',recover)
    d.run_download(store,root,new)
    assert store.get(new)['status']=='complete'
    assert Path(store.get(new)['path']).read_bytes()==body


def test_redirect_host_restriction(monkeypatch):
    class Redirect:
        status_code=302
        headers={'Location':'https://attacker.invalid/book.pdf'}
        def close(self):pass
    monkeypatch.setattr(d.requests,'get',lambda *a,**k:Redirect())
    with pytest.raises(ValueError,match='Untrusted'):
        d.safe_get('https://archive.org/download/book/example.pdf','archive')


def test_archive_mirror_fallback_preserved(tmp_path,monkeypatch):
    store,job,root=setup(tmp_path)
    url=store.get(job)['url']
    alt='https://ia600308.us.archive.org/12/items/id123/sample.txt'
    calls=[]
    monkeypatch.setattr(d,'archive_mirror_urls',lambda ident, canonical:[alt])
    monkeypatch.setattr(d.time,'sleep',lambda _:None)
    def switch(candidate,source):
        calls.append(candidate)
        if len(calls)<=2:
            raise requests.exceptions.Timeout('CDN unavailable')
        return Response(b'Public-domain text ' * 120)
    monkeypatch.setattr(d,'safe_get',switch)
    d.run_download(store,root,job)
    assert calls == [url,url,alt]
    assert store.get(job)['status']=='complete'
