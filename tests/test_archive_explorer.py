from concurrent.futures import ThreadPoolExecutor
import pytest
from bookharbor import archive_explorer as a


def demo_page(ids, next_cursor=None, total=1000):
    return ([{'identifier': id_, 'title': 'Mathematics', 'creator': ['A Writer'], 'year': '1880',
              'language': ['eng'], 'subject':['math'], 'mediatype':'texts'} for id_ in ids],next_cursor,total)


def test_filters_sanitize_solr_and_reject_unsafe():
    f=a.ArchiveFilters.parse({'query':'algebra OR mediatype:movies AND *', 'collection':'americana',
                              'year_from':'1850','year_to':'1920'})
    assert 'mediatype:texts' in f.expression()
    assert 'mediatype:movies' not in f.expression()
    assert 'collection:americana' in f.expression()
    with pytest.raises(ValueError):a.ArchiveFilters.parse({'query':'  '})
    with pytest.raises(ValueError):a.ArchiveFilters.parse({'query':'math','collection':'../evil'})
    with pytest.raises(ValueError):a.ArchiveFilters.parse({'query':'math','language':'*'})
    with pytest.raises(ValueError):a.ArchiveFilters.parse({'query':'math','year_from':'2020','year_to':'1900'})


def test_archive_scrape_params_and_cursor(monkeypatch):
    seen=[]
    class Response:
        def raise_for_status(self): pass
        def json(self):return {'items':[{'identifier':'abc','title':'Algebra'}], 'cursor':'next123','total':200}
    def get(url,params,timeout,headers):
        seen.append((url,params))
        return Response()
    monkeypatch.setattr(a.requests,'get',get)
    f=a.ArchiveFilters.parse({'query':'algebra'})
    rows,cursor,total=a.scrape_page(f)
    assert (len(rows),cursor,total)==(1,'next123',200)
    assert seen[0][1]['count']==100 and 'cursor' not in seen[0][1]
    with pytest.raises(a.CatalogError):a.scrape_page(f,'next123')


def test_archive_explorer_cursor_restart_dedup_and_local_filters(monkeypatch,tmp_path):
    pages = iter([demo_page(['id01','id02'], 'another'),demo_page(['id02','id03'])])
    monkeypatch.setattr(a,'scrape_page',lambda f,cursor=None:next(pages))
    db=a.ArchiveCatalog(tmp_path/'cat.sqlite3',min_spacing=0)
    first=db.start({'query':'mathematics', 'language':'en'})
    assert first['discovered']==2 and first['finished']==0
    sid=first['id']
    reopened=a.ArchiveCatalog(tmp_path/'cat.sqlite3',min_spacing=0)
    second=reopened.next_page(sid)
    assert second['finished']==1
    listing=reopened.list_items(sid)
    assert {b['id'] for b in listing['items']}=={'id01','id02','id03'}
    assert listing['total']==3
    assert reopened.list_items(sid,'Mathem')['total']==3
    assert reopened.list_items(sid,access='public')['total']==0
    reopened.mark_formats('id01', {'epub':'https://archive.org/download/id01/example.epub',
                                    'pdf':'https://evil.com/file.pdf'})
    assert reopened.list_items(sid,access='public')['total']==1
    assert 'epub' in reopened.record('id01')['formats']
    assert 'pdf' not in reopened.record('id01')['formats']
    assert reopened.stats()['indexed']==3
    assert reopened.next_page(sid)['finished']==1


def test_failed_page_does_not_advance_cursor(monkeypatch,tmp_path):
    db=a.ArchiveCatalog(tmp_path/'cat.sqlite3',min_spacing=0)
    calls=[0]
    def fetch(f,cursor=None):
        calls[0]+=1
        if calls[0]==1:raise a.CatalogError('timeout')
        return demo_page(['ok'])
    monkeypatch.setattr(a,'scrape_page',fetch)
    with pytest.raises(a.CatalogError):db.start({'subject':'history'})
    with db.connect() as con:
        session=con.execute('SELECT id FROM sessions').fetchone()[0]
    assert db.get_session(session)['page_count']==0
    assert db.next_page(session)['discovered']==1


def test_unsafe_metadata_never_indexed(monkeypatch,tmp_path):
    monkeypatch.setattr(a,'scrape_page',lambda f,cursor=None:([{'identifier':'../bad'},{'identifier':'valid-id','title':'Good'},'bogus'],None,None))
    db=a.ArchiveCatalog(tmp_path/'cat.sqlite3',min_spacing=0)
    state=db.start({'author':'Homer'})
    assert state['discovered']==1
    assert db.record('../bad') is None
    assert db.record('valid-id')['title']=='Good'


def test_concurrent_page_advancement_fetches_once(monkeypatch,tmp_path):
    calls=[]
    def fetch(f,cursor=None):
        calls.append(cursor)
        return demo_page(['A'], None)
    monkeypatch.setattr(a,'scrape_page',fetch)
    db=a.ArchiveCatalog(tmp_path/'cat.sqlite3',min_spacing=0)
    session=db.start({'query':'history'})['id']
    with ThreadPoolExecutor(max_workers=3) as pool:
        result=list(pool.map(lambda _:db.next_page(session),range(3)))
    assert all(x['finished'] for x in result)
    assert calls==[None]


def test_bounded_background_harvest_and_resume(monkeypatch,tmp_path):
    pages=[demo_page(['a'], 'c1'),demo_page(['b'], 'c2'),demo_page(['c'], None)]
    calls=[]
    def fetch(f,cursor=None):
        calls.append(cursor)
        return pages.pop(0)
    monkeypatch.setattr(a,'scrape_page',fetch)
    db=a.ArchiveCatalog(tmp_path/'archive.sqlite3',min_spacing=0)
    state=db.start({'subject':'math'})
    sid=state['id']
    with pytest.raises(ValueError):db.start_harvest(sid,0)
    with pytest.raises(ValueError):db.start_harvest(sid,51)
    db.start_harvest(sid,2)
    db._harvest_jobs[sid]['thread'].join(timeout=3)
    assert db.harvest_status(sid)['harvesting'] is False
    assert db.session_status(sid)['page_count']==3
    assert db.session_status(sid)['finished']
    assert db.stats()['indexed']==3
    assert calls==[None,'c1','c2']


def test_background_harvest_can_stop(monkeypatch,tmp_path):
    import threading
    gate=threading.Event()
    requested=threading.Event()
    calls=[]
    def fetch(f,cursor=None):
        calls.append(cursor)
        if cursor:
            requested.set()
            gate.wait(timeout=2)
        return demo_page([str(len(calls))], 'next'+str(len(calls)))
    monkeypatch.setattr(a,'scrape_page',fetch)
    db=a.ArchiveCatalog(tmp_path/'cat.sqlite3',min_spacing=0)
    sid=db.start({'collection':'americana'})['id']
    db.start_harvest(sid,20)
    assert requested.wait(timeout=2)
    db.stop_harvest(sid)
    gate.set()
    db._harvest_jobs[sid]['thread'].join(timeout=3)
    assert len(calls)==2
    assert db.session_status(sid)['finished']==0


def test_replayed_cursor_switches_to_bounded_advanced_search(monkeypatch,tmp_path):
    def scrape(f,cursor=None):
        if not cursor:
            return demo_page(['first','second'],'cursor-one')
        raise a.CatalogError('Archive returned the same cursor twice')
    calls=[]
    def fallback(f,page):
        calls.append(page)
        if page==1:
            return ([{'identifier':'first','title':'First'}, {'identifier':'third','title':'Third'}], 300)
        return ([{'identifier':'fourth','title':'Fourth'}],300)
    monkeypatch.setattr(a,'scrape_page',scrape)
    monkeypatch.setattr(a,'advancedsearch_page',fallback)
    db=a.ArchiveCatalog(tmp_path/'arc.sqlite3',min_spacing=0)
    session=db.start({'collection':'americana'})['id']
    state=db.next_page(session)
    assert state['mode']=='advanced' and state['fallback_page']==1
    assert state['finished']==0
    assert db.list_items(session)['total']==3
    state=db.next_page(session)
    assert state['fallback_page']==2
    assert db.list_items(session)['total']==4
    assert calls==[1,2]


def test_fallback_10000_limit_is_explicit(monkeypatch,tmp_path):
    def scrape(f,cursor=None):
        if cursor:
            raise a.CatalogError('Archive returned the same cursor twice')
        return demo_page(['first'],'cursor')
    monkeypatch.setattr(a,'scrape_page',scrape)
    monkeypatch.setattr(a,'advancedsearch_page',lambda f,page:([{'identifier':f'page-{page}'}],100000))
    db=a.ArchiveCatalog(tmp_path/'arc.sqlite3',min_spacing=0)
    sid=db.start({'query':'large'})['id']
    db.next_page(sid)
    with db.connect() as conn:
        conn.execute('UPDATE sessions SET fallback_page=99 WHERE id=?',(sid,))
    state=db.next_page(sid)
    assert state['finished']==1 and state['fallback_page']==100


def test_advancedsearch_rejects_page_above_limit():
    f=a.ArchiveFilters.parse({'subject':'mathematics'})
    with pytest.raises(a.CatalogError,match='10,000'):
        a.advancedsearch_page(f,101)
