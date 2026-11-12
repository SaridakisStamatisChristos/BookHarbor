"""Safe, bounded file downloader with temporary files, redirect limits and ledger."""
from __future__ import annotations
import hashlib
import re
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin
import requests
from .providers import allowed_url, archive_mirror_urls, HEADERS, MAX_FILE_BYTES
from .storage import Store

CHUNK = 128 * 1024

def clean_part(value: str, fallback: str = "Unknown") -> str:
    value = re.sub(r"[\\/\x00-\x1f<>:\"|?*]+", "-", value)
    value = re.sub(r"\s+", " ", value).strip(" .-")
    return (value[:85] or fallback)


def safe_get(url: str, source: str):
    """Validate every redirect, never following untrusted or private hosts."""
    for _ in range(6):
        if not allowed_url(url, source):
            raise ValueError("Untrusted download host or URL")
        response = requests.get(url, headers=HEADERS, stream=True,
                                timeout=(12, 65), allow_redirects=False)
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError("Redirect with no destination")
            url = urljoin(url, location)
            continue
        try:
            response.raise_for_status()
        except requests.RequestException:
            response.close()
            raise
        return response
    raise ValueError("Too many redirects")


def _transient_download_failure(exc: Exception) -> bool:
    """Retry transient GET failures, never HTTP 403/404 or unsafe URLs."""
    if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        code = exc.response.status_code if exc.response is not None else None
        return code in (429, 500, 502, 503, 504)
    return False


def run_download(store: Store, library_dir: Path, job_id: int):
    job = store.get(job_id)
    if not job:
        return
    store.update(job_id, "running")
    library_dir.mkdir(parents=True, exist_ok=True)
    name = clean_part(job["author"]) + " - " + clean_part(job["title"]) + " [" + clean_part(job["source"]) + "]." + job["format"]
    dest = library_dir / name
    dest = library_dir / (dest.stem + f" [job-{job_id}]" + dest.suffix)
    part = library_dir / f".{job_id}.part"
    transferred = 0
    try:
        # Retry the canonical URL, then try up to two public, metadata-approved
        # Archive storage nodes if the Archive CDN stalls. Never concatenate.
        urls = [job['url'], job['url']]
        for attempt in range(4):
            if attempt >= len(urls):
                break
            transferred = 0
            digest = hashlib.sha256()
            try:
                with safe_get(urls[attempt], job["source"]) as response:
                    length = response.headers.get("Content-Length", "")
                    if length and int(length) > MAX_FILE_BYTES:
                        raise ValueError("File exceeds 350 MiB size limit")
                    ctype = response.headers.get("Content-Type", "").lower()
                    if "text/html" in ctype or "application/json" in ctype:
                        raise ValueError("Server supplied a page/error instead of an ebook file")
                    with part.open("wb") as out:
                        for chunk in response.iter_content(chunk_size=CHUNK):
                            if not chunk:
                                continue
                            transferred += len(chunk)
                            if transferred > MAX_FILE_BYTES:
                                raise ValueError("File exceeds 350 MiB size limit")
                            out.write(chunk)
                            digest.update(chunk)
                break
            except requests.RequestException as exc:
                if not _transient_download_failure(exc):
                    raise
                if attempt == 1 and job["source"] in ("archive", "openlibrary"):
                    urls.extend(archive_mirror_urls(job["book_id"], job["url"])[:2])
                if attempt + 1 >= len(urls):
                    raise
                part.unlink(missing_ok=True)
                time.sleep(1.0)
                continue
        if transferred < 100:
            raise ValueError("Downloaded file is unexpectedly small")
        with part.open("rb") as check:
            header = check.read(256).lstrip()
        if header[:15].lower().startswith((b"<!doctype html", b"<html", b"<?xml")):
            raise ValueError("Received markup rather than book content")
        if job["format"] == "pdf" and not header.startswith(b"%PDF-"):
            raise ValueError("Downloaded file does not appear to be a PDF")
        if job["format"] == "epub" and not header.startswith(b"PK"):
            raise ValueError("Downloaded file does not appear to be an EPUB archive")
        if job["format"] == "epub" and not zipfile.is_zipfile(part):
            raise ValueError("Downloaded EPUB has an invalid ZIP structure")
        part.replace(dest)
        store.update(job_id, "complete", str(dest), transferred, sha256=digest.hexdigest())
    except Exception as exc:
        store.update(job_id, "failed", byte_count=transferred, error=str(exc))
    finally:
        part.unlink(missing_ok=True)
