"""Polite, API-first discovery for public/free ebook catalogs.

Each record is only an offer to inspect/download; it is not a copyright determination.
The Internet Archive adapter deliberately avoids lending, private, and DRM files.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import PurePosixPath
from urllib.parse import quote, urlparse
from xml.etree import ElementTree as ET

import requests

APP_CONTACT = os.environ.get("BOOKHARBOR_CONTACT", "https://github.com/")
USER_AGENT = f"BookHarbor/0.1 (local personal ebook finder; {APP_CONTACT})"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json, application/atom+xml;q=0.7, */*;q=0.5"}
TIMEOUT = (8, 22)
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
        }.get(source, ())
        return bool(host and any(host == root or host.endswith("." + root) for root in roots))
    except ValueError:
        return False


def get_json(url: str, *, params=None) -> dict:
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise CatalogError(str(exc)) from exc


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
    data = get_json("https://gutendex.com/books/", params=params)
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


def search_openlibrary(query: str, language: str = "", limit: int = MAX_RESULTS):
    # Discovery only; downloadable files resolve through Archive's public API.
    params = {"q": query, "limit": min(limit, 15),
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


SOURCES = {
    "gutenberg": search_gutenberg,
    "archive": search_archive,
    "openlibrary": search_openlibrary,
    "standard": search_standard,
}


def preferred_format(formats: dict[str, str], preference: str = "auto") -> tuple[str, str] | None:
    order = [preference] if preference in ("epub", "pdf", "txt", "mobi") else []
    order += ["epub", "pdf", "txt", "mobi"]
    for extension in order:
        if extension in formats:
            return extension, formats[extension]
    return None
