"""Temporary diagnostic for provider cursor caching; bounded requests, no downloads."""
import hashlib
import secrets
import requests
from bookharbor.archive_explorer import ArchiveFilters, FIELDS, SCRAPE_ENDPOINT
from bookharbor.providers import HEADERS

filters=ArchiveFilters.parse({'collection':'americana','subject':'mathematics'})
base={'q':filters.expression(),'fields':FIELDS,'count':100}

def check(name,params,headers=None):
    try:
        response=requests.get(SCRAPE_ENDPOINT,params=params,headers=headers or HEADERS,timeout=(12,25))
        response.raise_for_status(); data=response.json()
        items=data.get('items') or []
        cursor=data.get('cursor') or ''
        print('CURSOR PROBE',name,'status',response.status_code,'n',len(items),
            'first',items[0].get('identifier') if items else '',
            'last',items[-1].get('identifier') if items else '',
            'token_hash',hashlib.sha256(cursor.encode()).hexdigest()[:12],
            'request',response.url.split('cursor=')[0][:80],flush=True)
        return cursor
    except Exception as exc:
        print('CURSOR PROBE',name,'ERROR',str(exc)[:200],flush=True)
        return ''

cursor=check('first',base)
if cursor:
    second={**base,'cursor':cursor}
    check('normal',second)
    check('no-cache-headers',second,{**HEADERS,'Cache-Control':'no-cache, no-store','Pragma':'no-cache'})
    check('cachebuster',{**second,'_':secrets.token_hex(6)},{**HEADERS,'Cache-Control':'no-cache'})
    check('explicit-sort',{**second,'sorts':'identifier'})