"""Real Internet Archive cursor search; metadata only, limited to 200 records."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from bookharbor.archive_explorer import ArchiveCatalog


def main():
    with tempfile.TemporaryDirectory(prefix='bookharbor-archive-live-') as work:
        catalog=ArchiveCatalog(Path(work)/'catalog.sqlite3',min_spacing=0.5)
        first=catalog.start({'collection':'americana', 'subject':'mathematics'})
        if not (1 <= first['discovered'] <= 100):
            raise RuntimeError('Archive returned an empty first cursor page')
        records=catalog.list_items(first['id'], limit=50)
        assert records['total'] > 0 and all(b['id'] for b in records['items'])
        print('ARCHIVE LIVE FIRST PAGE',json.dumps({'count':first['discovered'],
             'session':first['id'], 'finished':first['finished'],
             'catalog_total':catalog.stats()['indexed']}),flush=True)
        if not first['finished']:
            next_page=catalog.next_page(first['id'])
            assert next_page['page_count']==2
            assert next_page['discovered'] >= first['discovered']
            assert catalog.stats()['indexed']>=first['discovered']
            print('ARCHIVE LIVE SECOND PAGE',json.dumps({'count':next_page['discovered'],
                  'pages':next_page['page_count'],'finished':next_page['finished']}),flush=True)
    print('ARCHIVE CURSOR LIVE PASS',flush=True)


if __name__=='__main__':
    main()
