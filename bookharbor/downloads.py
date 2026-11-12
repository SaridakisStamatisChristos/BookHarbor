"""Safe, bounded file downloader with temporary files, redirect limits and ledger."""
from __future__ import annotations
import re
import time
from pathlib import Path
from urllib.parse import urljoin
import requests
from .providers import allowed_url, HEADERS, MAX_FILE_BYTES
from .storage import Store

CHUNK = 128 * 1024

def clean_part(value: str, fallback: str = "Unknown") -> str:
    value = re.sub(r"[\\/\x00-\x1f<>:\"|?*]+", "-", value)
    value = re.sub(r"\s+", " ", value).strip(" .-")
    return (value[:85] or fallback)


def safe_get(url: str, source: str):
    """Reject untrusted redirects and URLs before reading response bodies."""
    for _ in range(6):
        if not allowed_url(url, source):
            raise ValueError("Untrusted download host or URL")
        response = requests.get(url, headers=HEADERS, stream=True, timeout=(8, 60), allow_redirects=False)
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError("Redirect with no destination")
            url = urljoin(url, location)
            continue
        response.raise_for_status()
        return response
    raise ValueError("Too many redirects")


def run_download(store: Store, library_dir: Path, job_id: int):
    job = store.get(job_id)
    if not job:
        return
    store.update(job_id, "running")
    library_dir.mkdir(parents=True, exist_ok=True)
    name = clean_part(job["author"]) + " - " + clean_part(job["title"]) + " [" + clean_part(job["source"]) + "]." + job["format"]
    dest = library_dir / name
    if dest.exists():
        dest = library_dir / (dest.stem + f" [{job_id}]" + dest.suffix)
    part = library_dir / f".{job_id}.part"
    transferred = 0
    try:
        with safe_get(job["url"], job["source"]) as response:
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
        if transferred < 100:
            raise ValueError("Downloaded file is unexpectedly small")
        # Minimal format signature check avoids saving obvious HTML or error pages.
        with part.open("rb") as check:
            header = check.read(256).lstrip()
        if header[:15].lower().startswith((b"<!doctype html", b"<html", b"<?xml")):
            raise ValueError("Received markup rather than book content")
        if job["format"] == "pdf" and not header.startswith(b"%PDF-"):
            raise ValueError("Downloaded file does not appear to be a PDF")
        if job["format"] == "epub" and not header.startswith(b"PK"):
            raise ValueError("Downloaded file does not appear to be an EPUB archive")
        part.replace(dest)
        store.update(job_id, "complete", str(dest), transferred)
    except Exception as exc:
        store.update(job_id, "failed", byte_count=transferred, error=str(exc))
    finally:
        part.unlink(missing_ok=True)
