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

# OAI-PMH is a published bulk metadata interface, not a search API.
from xml.etree import ElementTree as ET
try:
    r=requests.get("https://library.oapen.org/oai/request",params={"verb":"ListRecords","metadataPrefix":"oai_dc"},timeout=(5,15))
    print("oapen-listrecords",r.status_code,"bytes",len(r.content),flush=True)
    if r.status_code == 200:
        root=ET.fromstring(r.content)
        ns={"oai":"http://www.openarchives.org/OAI/2.0/","dc":"http://purl.org/dc/elements/1.1/"}
        records=root.findall(".//oai:record", ns)
        for record in records[:2]:
            print("oapen-record-sample",
                  "titles",[x.text for x in record.findall(".//dc:title", ns)][:2],
                  "ids",[x.text for x in record.findall(".//dc:identifier", ns)][:5],flush=True)
        print("oapen-oai-page","records",len(records),"next",bool(root.find(".//oai:resumptionToken",ns) is not None),flush=True)
except Exception as exc:
    print("oapen-oai-listrecords-error",str(exc)[:230],flush=True)
