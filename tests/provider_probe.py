"""One-shot diagnostic of official catalog endpoints. No scraping or files stored."""
import requests
sources = [
    ("gutenberg-opds", "https://www.gutenberg.org/ebooks/search.opds/?query=alice"),
    ("gutenberg-gutendex", "https://gutendex.com/books/?search=alice"),
    ("oapen-rest", "https://library.oapen.org/rest/search?query=philosophy&limit=1"),
    ("oapen-oai", "https://library.oapen.org/oai/request?verb=Identify"),
    ("oapen-dspace7", "https://library.oapen.org/server/api/discover/search/objects?query=philosophy&dsoType=item&size=1"),
    ("oapen-feed", "https://memo.doabooks.org/file/oapen/OAPENLibrary_KBART_books.tsv"),
    ("oapen-json", "https://memo.doabooks.org/file/oapen/OAPENLibrary.json"),
]
for label,url in sources:
    try:
        r=requests.get(url,timeout=(5,9),stream=True,headers={"User-Agent":"BookHarbor/0.2 metadata probe (https://github.com/SaridakisStamatisChristos/BookHarbor)","Accept":"application/json, application/atom+xml, text/tab-separated-values, */*"})
        print(label, r.status_code, r.url, "type",r.headers.get("Content-Type",""),"length",r.headers.get("Content-Length",""),flush=True)
        r.close()
    except requests.RequestException as e:
        print(label,type(e).__name__,str(e)[:180],flush=True)
