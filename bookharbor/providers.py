"""Polite, API-first discovery for public/free ebook catalogs.

Each record is only an offer to inspect/download; it is not a copyright determination.
The Internet Archive adapter deliberately avoids lending, private, and DRM files.
"""
from __future__ import annotations

import os
import re
import time
from functools import lru_cache
from pathlib import PurePosixPath
from urllib.parse import quote, urlparse, urljoin
from xml.etree import ElementTree as ET

import requests

APP_CONTACT = os.environ.get("BOOKHARBOR_CONTACT", "https://github.com/")
USER_AGENT = f"BookHarbor/0.2 (local personal ebook finder; {APP_CONTACT})"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json, application/atom+xml;q=0.7, */*;q=0.5"}
TIMEOUT = (12, 28)
MAX_RESULTS = 12
MAX_FILE_BYTES = 350 * 1024 * 1024

class CatalogError(Exception):
    pass


def safe_identifier(identifier: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]{1,110}", str(identifier))) and ".." not in str(identifier)


def safe_file_name(value: str) -> bool:
    if not value or len(value) > 300 or "\\" in value or "\x00" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(p not in ("", "..", ".") for p in path.parts)


def allowed_url(url: str, source: str) -> bool:
    """No arbitrary local/private/third-party URLs from untrusted catalog metadata."""
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
            return False
        host = (parsed.hostname or "").lower()
        roots = {
            "gutenberg": ("gutenberg.org",),
            "archive": ("archive.org",),
            "openlibrary": ("archive.org",),
            "standard": ("standardebooks.org",),
            "oapen": ("oapen.org",),
        }.get(source, ())
        return bool(host and any(host == root or host.endswith("." + root) for root in roots))
    except ValueError:
        return False


def get_json(url: str, *, params=None) -> dict:
    """Retry temporary upstream errors once; never retry permission failures."""
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                resp.close()
                time.sleep(0.7)
                continue
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            if attempt == 0:
                time.sleep(0.7)
                continue
            raise CatalogError(str(exc)) from exc
        except (requests.RequestException, ValueError) as exc:
            raise CatalogError(str(exc)) from exc
    raise CatalogError(f"Catalog unavailable at {url}")


def display_name(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value[:3] if v)
    return str(value or "Unknown")


def format_from_mime(mime: str, url: str) -> str | None:
    mime = mime.lower().split(";")[0].strip()
    suffix = urlparse(url).path.lower()
    if mime == "application/epub+zip" or suffix.endswith((".epub", ".epub3", ".epub.images", ".epub.noimages")) or ".epub3." in suffix:
        return "epub"
    if mime == "application/pdf" or suffix.endswith(".pdf"):
        return "pdf"
    if mime.startswith("text/plain") or suffix.endswith((".txt", ".txt.utf-8")):
        return "txt"
    if "mobipocket" in mime or suffix.endswith((".mobi", ".azw", ".azw3")):
        return "mobi"
    return None


def search_gutenberg(query: str, language: str = "", limit: int = MAX_RESULTS):
    params = {"search": query}
    if language and re.fullmatch(r"[a-z]{2,3}", language):
        params["languages"] = language
    try:
        data = get_json("https://gutendex.com/books/", params=params)
    except CatalogError as first_error:
        # Project Gutenberg's official machine-readable OPDS is the fallback.
        try:
            return search_gutenberg_opds(query, language, limit)
        except CatalogError as fallback_error:
            raise CatalogError(
                f"Gutendex unavailable ({first_error}); Gutenberg OPDS unavailable ({fallback_error})"
            ) from fallback_error
    output = []
    for item in data.get("results", [])[:limit]:
        raw_formats = item.get("formats") or {}
        formats = {}
        for mime, url in raw_formats.items():
            if not isinstance(url, str) or not allowed_url(url, "gutenberg"):
                continue
            ext = format_from_mime(mime, url)
            if ext and ext not in formats:
                formats[ext] = url
        authors = ", ".join(a.get("name", "") for a in item.get("authors", []) if isinstance(a, dict))
        book_id = str(item.get("id", ""))
        if not book_id.isdecimal():
            continue
        output.append({
            "source": "gutenberg", "id": book_id,
            "title": str(item.get("title") or "Untitled"),
            "author": authors or "Unknown", "year": "",
            "page": f"https://www.gutenberg.org/ebooks/{book_id}",
            "formats": formats, "access": "Public Gutenberg download",
        })
    return output


def search_gutenberg_opds(query: str, language: str = "", limit: int = MAX_RESULTS):
    """Official Gutenberg OPDS 1 Atom fallback with acquisition-only links.

    Gutenberg plans to sunset the XML OPDS feed in 2027; Gutendex stays primary.
    """
    atom = "{http://www.w3.org/2005/Atom}"
    dc = "{http://purl.org/dc/terms/}"
    try:
        response = requests.get(
            "https://www.gutenberg.org/ebooks/search.opds/",
            headers={**HEADERS, "Accept": "application/atom+xml;profile=opds-catalog"},
            params={"query": query}, timeout=TIMEOUT,
        )
        response.raise_for_status()
        if len(response.content) > 2_000_000:
            raise CatalogError("Gutenberg OPDS feed exceeds size limit")
        root = ET.fromstring(response.content)
    except (requests.RequestException, ET.ParseError) as exc:
        raise CatalogError(str(exc)) from exc
    if root.tag != f"{atom}feed":
        raise CatalogError("Gutenberg OPDS returned a non-Atom response")
    output = []
    for entry in root.findall(f"{atom}entry"):
        title = entry.findtext(f"{atom}title", default="Untitled")
        author = entry.findtext(f"{atom}author/{atom}name", default="Unknown")
        entry_id = entry.findtext(f"{atom}id", default="")
        formats = {}
        page = ""
        for link in entry.findall(f"{atom}link"):
            href = link.attrib.get("href", "")
            rel = link.attrib.get("rel", "")
            mime = link.attrib.get("type", "")
            full = urljoin("https://www.gutenberg.org/", href)
            if not allowed_url(full, "gutenberg"):
                continue
            if rel == "alternate" and mime.startswith("text/html"):
                page = full
            if rel.startswith("http://opds-spec.org/acquisition") and rel not in (
                "http://opds-spec.org/acquisition/borrow",
                "http://opds-spec.org/acquisition/buy",
            ):
                ext = format_from_mime(mime, full)
                if ext:
                    formats.setdefault(ext, full)
        match = re.search(r"/ebooks/(\d+)(?:[/?#]|$)", entry_id) or re.search(
            r"/ebooks/(\d+)(?:[/?#]|$)", page
        )
        if not match:
            continue
        book_id = match.group(1)
        if language:
            languages = [n.text or "" for n in entry.findall(f"{dc}language")]
            if languages and not any(value.lower().startswith(language.lower()) for value in languages):
                continue
        output.append({
            "source": "gutenberg", "id": book_id,
            "title": title, "author": author, "year": "",
            "page": f"https://www.gutenberg.org/ebooks/{book_id}",
            "formats": formats, "access": "Public Gutenberg OPDS catalog",
        })
        if len(output) >= limit:
            break
    return output


def search_archive(query: str, language: str = "", limit: int = MAX_RESULTS):
    # Quote only user words, never pass Lucene operators supplied by the user.
    terms = re.findall(r"[^\W_][\w'-]*", query, flags=re.UNICODE)[:7]
    if not terms:
        return []
    clean = " ".join(re.sub(r"[^\w'-]", "", t) for t in terms)
    expression = f'mediatype:texts AND (title:({clean}) OR creator:({clean}) OR subject:({clean}))'
    params = {"q": expression, "output": "json", "rows": min(limit, 15),
              "fl[]": ["identifier", "title", "creator", "year", "language"],
              "sort[]": "downloads desc"}
    data = get_json("https://archive.org/advancedsearch.php", params=params)
    output = []
    for item in (data.get("response") or {}).get("docs", []):
        identifier = str(item.get("identifier", ""))
        if not safe_identifier(identifier):
            continue
        if language:
            langs = item.get("language", [])
            langs = langs if isinstance(langs, list) else [langs]
            if langs and not any(str(v).lower().startswith(language.lower()) for v in langs):
                continue
        output.append({
            "source": "archive", "id": identifier,
            "title": display_name(item.get("title")),
            "author": display_name(item.get("creator")),
            "year": display_name(item.get("year")) if item.get("year") else "",
            "page": f"https://archive.org/details/{quote(identifier)}",
            "formats": {}, "access": "Availability checked when selected",
        })
    return output


def _is_true(value) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes")


def archive_formats(identifier: str) -> dict[str, str]:
    """Inspect public metadata; no lending, restricted files, or DRM containers."""
    if not safe_identifier(identifier):
        raise CatalogError("Invalid Internet Archive identifier")
    data = get_json(f"https://archive.org/metadata/{quote(identifier)}")
    md = data.get("metadata") or {}
    if not isinstance(md, dict):
        return {}
    if any(_is_true(md.get(k)) for k in ("is_dark", "is_restricted", "access-restricted", "access-restricted-item")):
        return {}
    status = str(md.get("lending___status") or "").upper()
    if status and status not in ("NOT_LENDABLE", "NONE"):
        return {}
    # Lending metadata can occur on the item's detail page, not only in files.
    if md.get("lendingInfo") or data.get("lendingInfo"):
        return {}
    options = {}
    files = data.get("files") or []
    for item in files:
        if not isinstance(item, dict) or _is_true(item.get("private")):
            continue
        name = str(item.get("name", ""))
        if not safe_file_name(name):
            continue
        low = name.lower()
        if any(x in low for x in ("_meta.", "_files.", "_scandata.", "_abbyy", "_djvu.xml", "_archive.torrent", "_encrypted")):
            continue
        size = item.get("size", 0)
        try:
            if int(size) > MAX_FILE_BYTES:
                continue
        except (ValueError, TypeError):
            continue
        suffix = low.rsplit(".", 1)[-1]
        ext = {"epub": "epub", "pdf": "pdf", "txt": "txt", "mobi": "mobi"}.get(suffix)
        if ext and ext not in options:
            options[ext] = f"https://archive.org/download/{quote(identifier)}/{quote(name, safe='/')}"
    return options


def archive_mirror_urls(identifier: str, canonical: str) -> list[str]:
    """Official Archive metadata may offer two redundant public storage nodes.

    These links are *only* for an already approved open file. Do not use
    arbitrary hosts, filenames, private files, or other item paths.
    """
    if not safe_identifier(identifier):
        return []
    expected_prefix = f"https://archive.org/download/{quote(identifier)}/"
    if not canonical.startswith(expected_prefix):
        return []
    file_name = canonical[len(expected_prefix):]
    if not safe_file_name(file_name) or "?" in file_name or "#" in file_name:
        return []
    # Recheck that the exact requested file is currently publicly offered.
    try:
        approved = archive_formats(identifier)
        if canonical not in approved.values():
            return []
        md = get_json(f"https://archive.org/metadata/{quote(identifier)}")
    except CatalogError:
        return []
    directory = str(md.get("dir") or "")
    if not re.fullmatch(r"/[0-9]+/items/" + re.escape(identifier), directory):
        return []
    mirrors = []
    for key in ("d1", "d2"):
        host = str(md.get(key) or "").lower()
        if not re.fullmatch(r"ia[0-9]{5,8}\.[a-z]{2}\.archive\.org", host):
            continue
        url = f"https://{host}{directory}/{file_name}"
        if allowed_url(url, "archive") and url not in mirrors:
            mirrors.append(url)
    return mirrors


def search_openlibrary(query: str, language: str = "", limit: int = MAX_RESULTS):
    # Discovery only; downloadable files resolve through Archive's public API.
    params = {"q": query, "limit": min(limit, 15), "public_scan": "true",
              "fields": "key,title,author_name,first_publish_year,ebook_access,ia,language"}
    if language:
        params["language"] = language
    data = get_json("https://openlibrary.org/search.json", params=params)
    output = []
    for doc in data.get("docs", []):
        if doc.get("ebook_access") != "public":
            continue
        identifier = next((v for v in doc.get("ia", []) if safe_identifier(str(v))), "")
        key = str(doc.get("key") or "")
        if not re.fullmatch(r"/works/OL\d+W", key):
            continue
        output.append({
            "source": "openlibrary", "id": identifier,
            "title": str(doc.get("title") or "Untitled"),
            "author": display_name(doc.get("author_name")),
            "year": str(doc.get("first_publish_year") or ""),
            "page": "https://openlibrary.org" + key,
            "formats": {}, "access": "Public scan; inspect Archive formats" if identifier else "Read via Open Library",
        })
    return output


def search_standard(query: str, language: str = "", limit: int = MAX_RESULTS):
    """Search only the public *recent releases* feed, not the patrons-only full OPDS catalog."""
    if language and language not in ("en", "eng"):
        return []
    url = "https://standardebooks.org/feeds/atom/new-releases"
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except (requests.RequestException, ET.ParseError) as exc:
        raise CatalogError(str(exc)) from exc
    atom = "{http://www.w3.org/2005/Atom}"
    q = query.casefold().strip()
    output = []
    for entry in root.findall(f"{atom}entry"):
        title = entry.findtext(f"{atom}title", default="Untitled")
        author = entry.findtext(f"{atom}author/{atom}name", default="Unknown")
        if q and not all(part in (title + " " + author).casefold() for part in q.split()):
            continue
        page, formats = "", {}
        for link in entry.findall(f"{atom}link"):
            href = link.attrib.get("href", "")
            rel = link.attrib.get("rel", "alternate")
            mime = link.attrib.get("type", "")
            if not allowed_url(href, "standard"):
                continue
            if rel in ("alternate", "") and not page:
                page = href
            ext = format_from_mime(mime, href)
            if ext and rel in ("enclosure", "http://opds-spec.org/acquisition", "alternate"):
                formats.setdefault(ext, href)
        if not page:
            continue
        output.append({
            "source": "standard", "id": page.rsplit("/", 1)[-1],
            "title": title, "author": author, "year": "", "page": page,
            "formats": formats, "access": "Recent releases only",
        })
        if len(output) >= limit:
            break
    return output



@lru_cache(maxsize=1)
def _oapen_oai_recent_records() -> tuple[dict, ...]:
    """Bounded OAI-PMH sample, not a complete search of OAPEN.

    OAI metadata contains item identifiers and sometimes download URLs, but
    generally no searchable full-catalog endpoint. Never invent file links.
    """
    ns = {"oai": "http://www.openarchives.org/OAI/2.0/",
          "dc": "http://purl.org/dc/elements/1.1/"}
    params = {"verb": "ListRecords", "metadataPrefix": "oai_dc"}
    records = []
    for page in range(3):
        try:
            response = requests.get("https://library.oapen.org/oai/request",
                                    headers={**HEADERS, "Accept": "application/xml"},
                                    params=params, timeout=TIMEOUT)
            response.raise_for_status()
            if len(response.content) > 3_000_000:
                raise CatalogError("OAPEN OAI metadata page too large")
            root = ET.fromstring(response.content)
        except (requests.RequestException, ET.ParseError) as exc:
            if records:
                break
            raise CatalogError(f"OAPEN OAI metadata unavailable: {exc}") from exc
        if root.find(".//oai:error", ns) is not None:
            if records:
                break
            raise CatalogError("OAPEN OAI returned a metadata error")
        for record in root.findall(".//oai:ListRecords/oai:record", ns):
            metadata = record.find("oai:metadata", ns)
            if metadata is None:
                continue
            def values(tag):
                return [element.text.strip() for element in metadata.findall(f".//dc:{tag}", ns)
                        if element.text and element.text.strip()]
            ids = values("identifier")
            handle = next((m.group(1) for value in ids if
                           (m := re.search(r"library\.oapen\.org/handle/([A-Za-z0-9.\-]+/[A-Za-z0-9.\-]+)", value))), None)
            if not handle:
                continue
            formats = {}
            for url in ids:
                if not allowed_url(url, "oapen"):
                    continue
                ext = format_from_mime("", url)
                if ext:
                    formats.setdefault(ext, url)
            records.append({
                "source": "oapen", "id": handle,
                "title": (values("title") or ["Untitled"])[0],
                "author": display_name(values("creator")),
                "year": (values("date") or [""])[0][:4],
                "languages": values("language"),
                "subjects": values("subject"),
                "page": "https://library.oapen.org/handle/" + quote(handle, safe="/"),
                "formats": formats,
                "access": "OAPEN OAI: recent metadata sample only; open item for other formats",
            })
        token = root.findtext(".//oai:ListRecords/oai:resumptionToken", default="", namespaces=ns)
        if not token or not token.strip() or page == 2:
            break
        params = {"verb": "ListRecords", "resumptionToken": token.strip()}
    return tuple(records)


def search_oapen_oai(query: str, language: str = "", limit: int = MAX_RESULTS):
    terms = [part.casefold() for part in query.split() if part.strip()]
    found = []
    for record in _oapen_oai_recent_records():
        langs = record.get("languages", [])
        if language and langs and not any(v.lower().startswith(language.lower()) for v in langs):
            continue
        searchable = " ".join([record["title"], record["author"], *record["subjects"]]).casefold()
        if not all(term in searchable for term in terms):
            continue
        found.append({k: v for k, v in record.items() if k not in ("subjects", "languages")})
        if len(found) >= limit:
            break
    return found


def search_oapen(query: str, language: str = "", limit: int = MAX_RESULTS):
    """Discover open-access academic books using OAPEN's documented REST search API.

    Only direct PDF/EPUB/TXT/MOBI links hosted on oapen.org are offered.
    The metadata and attached files are returned by the OAPEN repository itself.
    """
    terms = re.findall(r"[^\W_][\w'-]*", query, flags=re.UNICODE)[:6]
    if not terms:
        return []
    # Plain terms prevent caller-supplied Lucene operators from becoming search commands.
    clean = ' '.join(re.sub(r"[^\w'-]", '', part) for part in terms)
    try:
        data = get_json('https://library.oapen.org/rest/search',
                        params={'query': clean, 'expand': 'metadata,bitstreams', 'limit': min(limit, 15)})
    except CatalogError:
        # OAPEN REST can return 403; OAI is an official alternative but only
        # this small recent-record sample is searched unless REST succeeds.
        return search_oapen_oai(query, language, limit)
    entries = data if isinstance(data, list) else data.get('items', [])
    output = []
    for item in entries[:limit]:
        if not isinstance(item, dict) or item.get('type', 'item') != 'item':
            continue
        handle = str(item.get('handle', ''))
        if not re.fullmatch(r'[A-Za-z0-9.\-]{4,45}/[A-Za-z0-9.\-]{1,75}', handle):
            continue
        md = {}
        for field in item.get('metadata', []):
            if isinstance(field, dict) and field.get('key') and field.get('value'):
                md.setdefault(str(field['key']), []).append(str(field['value']))
        languages = md.get('dc.language.iso', []) + md.get('dc.language', [])
        if language and languages and not any(value.lower().startswith(language.lower()) for value in languages):
            continue
        title = (md.get('dc.title') or [item.get('name') or 'Untitled'])[0]
        authors = md.get('dc.contributor.author') or md.get('dc.creator') or []
        year = (md.get('dc.date.issued') or [''])[0][:4]
        formats = {}
        for b in item.get('bitstreams', []) or []:
            if not isinstance(b, dict) or b.get('bundleName') not in ('ORIGINAL', None, ''):
                continue
            relative = b.get('retrieveLink')
            name = str(b.get('name') or '')
            if not isinstance(relative, str) or not relative.startswith('/'):
                continue
            url = urljoin('https://library.oapen.org', relative)
            if not allowed_url(url, 'oapen'):
                continue
            ext = format_from_mime(str(b.get('mimeType') or ''), name)
            if ext and ext not in formats:
                try:
                    if int(b.get('sizeBytes', 0)) > MAX_FILE_BYTES:
                        continue
                except (ValueError, TypeError):
                    continue
                formats[ext] = url
        output.append({
            'source': 'oapen', 'id': handle,
            'title': title, 'author': display_name(authors), 'year': year,
            'page': 'https://library.oapen.org/handle/' + quote(handle, safe='/'),
            'formats': formats, 'access': 'Open-access academic book; check item license',
        })
    return output


SOURCES = {
    "gutenberg": search_gutenberg,
    "archive": search_archive,
    "openlibrary": search_openlibrary,
    "standard": search_standard,
    "oapen": search_oapen,
}


def preferred_format(formats: dict[str, str], preference: str = "auto") -> tuple[str, str] | None:
    order = [preference] if preference in ("epub", "pdf", "txt", "mobi") else []
    order += ["epub", "pdf", "txt", "mobi"]
    for extension in order:
        if extension in formats:
            return extension, formats[extension]
    return None
