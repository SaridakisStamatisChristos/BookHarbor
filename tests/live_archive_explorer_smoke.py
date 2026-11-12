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
            progress = first
            for _ in range(3):
                progress=catalog.next_page(first['id'])
                assert progress['page_count']>first['page_count']
                assert progress['discovered'] >= first['discovered']
                print('ARCHIVE LIVE CONTINUATION',json.dumps({'count':progress['discovered'],
                      'pages':progress['page_count'],'mode':progress['mode'],
                      'finished':progress['finished']}),flush=True)
                if progress['discovered'] > first['discovered'] or progress['finished']:
                    break
            if progress['discovered'] <= first['discovered'] and not progress['finished']:
                raise RuntimeError('Second page made no indexing progress even after fallback')
            assert catalog.stats()['indexed'] >= first['discovered']
    print('ARCHIVE DEEP INDEX LIVE PASS',flush=True)


if __name__=='__main__':
    main()
