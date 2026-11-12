"""Bounded downloads with verified, validator-gated HTTP Range resume support.

Only retries GET requests. All redirects are checked against provider allowlists.
Partial files are reused *only* with an ETag or Last-Modified validator.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin

import requests

from .providers import allowed_url, HEADERS, MAX_FILE_BYTES
from .storage import Store

CHUNK = 128 * 1024
RANGE = re.compile(r'^bytes (\d+)-(\d+)/(\d+|\*)$', re.I)


def clean_part(value: str, fallback: str = 'Unknown') -> str:
    value = re.sub(r'[\\/\x00-\x1f<>:"|?*]+', '-', str(value))
    value = re.sub(r'\s+', ' ', value).strip(' .-')
    return (value[:85] or fallback)


def safe_get(url: str, source: str, *, extra_headers: dict | None = None):
    """Allow only pre-approved HTTPS redirect targets, without following automatically."""
    headers = dict(HEADERS)
    if extra_headers:
        if any(key.lower() not in ('range', 'if-range') for key in extra_headers):
            raise ValueError('Unexpected request header for download')
        headers.update(extra_headers)
    for _ in range(6):
        if not allowed_url(url, source):
            raise ValueError('Untrusted download host or URL')
        response = requests.get(url, headers=headers, stream=True, timeout=(12, 65), allow_redirects=False)
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get('Location')
            response.close()
            if not location:
                raise ValueError('Redirect without destination')
            url = urljoin(url, location)
            continue
        try:
            response.raise_for_status()
        except requests.RequestException:
            response.close()
            raise
        return response
    raise ValueError('Too many redirects')


def _transient(exc: Exception) -> bool:
    if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
                        requests.exceptions.ChunkedEncodingError)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        code = exc.response.status_code if exc.response is not None else None
        return code in (429, 500, 502, 503, 504)
    return False


def _validator(headers) -> str | None:
    etag = str(headers.get('ETag', '')).strip()
    # Weak ETags are unsuitable for If-Range; use Last-Modified if available.
    if etag and not etag.startswith('W/') and len(etag) <= 200:
        return etag
    modified = str(headers.get('Last-Modified', '')).strip()
    if modified and len(modified) <= 100:
        return modified
    return None


def _load_partial(part: Path, meta: Path, url: str) -> tuple[int, str | None]:
    try:
        record = json.loads(meta.read_text(encoding='utf8'))
        count = part.stat().st_size
        if (record.get('url') == url and record.get('size') == count
                and isinstance(record.get('validator'), str)
                and record['validator'] and 0 < count < MAX_FILE_BYTES):
            return count, record['validator']
    except (OSError, ValueError, TypeError, KeyError):
        pass
    part.unlink(missing_ok=True)
    meta.unlink(missing_ok=True)
    return 0, None


def _save_partial(meta: Path, url: str, size: int, validator: str | None):
    if validator and size:
        tmp = meta.with_suffix('.tmp')
        tmp.write_text(json.dumps({'url': url, 'size': size,
                                   'validator': validator}), encoding='utf8')
        tmp.replace(meta)
    else:
        meta.unlink(missing_ok=True)


def _check_response(response, offset: int) -> tuple[str, int | None]:
    """Return write mode and expected total length, validating the server's range."""
    status = getattr(response, 'status_code', 200)
    ctype = response.headers.get('Content-Type', '').lower()
    if 'text/html' in ctype or 'application/json' in ctype or 'application/xml' in ctype:
        raise ValueError('Received markup/error response instead of a book')
    size_header = response.headers.get('Content-Length', '')
    length = int(size_header) if size_header and hasattr(response, 'status_code') else None
    if length is not None and (length < 0 or length > MAX_FILE_BYTES):
        raise ValueError('Invalid or oversized file length')
    if status == 206:
        if not offset:
            raise ValueError('Unexpected partial response without range request')
        match = RANGE.fullmatch(response.headers.get('Content-Range',''))
        if not match or int(match.group(1)) != offset:
            raise ValueError('Mismatched Content-Range offset')
        start, end = int(match.group(1)), int(match.group(2))
        full = int(match.group(3)) if match.group(3) != '*' else None
        if end < start or (full is not None and (full > MAX_FILE_BYTES or end >= full)):
            raise ValueError('Invalid Content-Range bounds')
        if length is not None and length != end - start + 1:
            raise ValueError('Content-Length disagrees with Content-Range')
        return 'ab', full
    if status == 200:
        # Correct if server ignores Range: restart rather than appending duplicates.
        return 'wb', length
    raise ValueError(f'Unexpected HTTP {status}')


def _validate_book(part: Path, fmt: str, byte_count: int):
    if byte_count < 100:
        raise ValueError('Downloaded file is unexpectedly small')
    with part.open('rb') as reader:
        head = reader.read(256).lstrip()
    if head[:15].lower().startswith((b'<!doctype html', b'<html', b'<?xml')):
        raise ValueError('Received markup rather than ebook data')
    if fmt == 'pdf' and not head.startswith(b'%PDF-'):
        raise ValueError('PDF signature not found')
    if fmt == 'epub' and (not head.startswith(b'PK') or not zipfile.is_zipfile(part)):
        raise ValueError('Invalid EPUB ZIP structure')


def run_download(store: Store, library_dir: Path, job_id: int):
    job = store.get(job_id)
    if not job:
        return
    store.update(job_id, 'running')
    library_dir.mkdir(parents=True, exist_ok=True)
    name = (clean_part(job['author']) + ' - ' + clean_part(job['title']) +
            ' [' + clean_part(job['source']) + '].' + job['format'])
    dest = library_dir / (Path(name).stem + f' [job-{job_id}]' + Path(name).suffix)
    # Per-edition key remains stable across retries with newly allocated job IDs.
    key = hashlib.sha256((job['source'] + '\0' + job['book_id'] + '\0' +
                          job['format'] + '\0' + job['url']).encode('utf8')).hexdigest()[:24]
    part = library_dir / ('.partial-' + key + '.part')
    meta = library_dir / ('.partial-' + key + '.json')
    transferred = 0
    try:
        for attempt in range(2):
            offset, prior_validator = _load_partial(part, meta, job['url'])
            extras = {'Range':f'bytes={offset}-', 'If-Range':prior_validator} if offset else None
            validator = prior_validator if offset else None
            transferred = 0
            try:
                with (safe_get(job['url'], job['source'], extra_headers=extras) if extras
                      else safe_get(job['url'], job['source'])) as response:
                    mode, expected_total = _check_response(response, offset)
                    if mode == 'wb':
                        offset = 0
                    validator = _validator(response.headers) or (prior_validator if mode == 'ab' else None)
                    with part.open(mode) as stream:
                        # Store validator before reading so interruption can resume.
                        # Once a write fails we update the recorded file size.
                        for chunk in response.iter_content(chunk_size=CHUNK):
                            if not chunk:
                                continue
                            if offset + len(chunk) + transferred > MAX_FILE_BYTES:
                                raise ValueError('File exceeds 350 MiB')
                            stream.write(chunk)
                            transferred += len(chunk)
                        stream.flush()
                total = part.stat().st_size
                if expected_total is not None and total != expected_total:
                    raise requests.exceptions.ChunkedEncodingError('Incomplete file transfer')
                _validate_book(part, job['format'], total)
                digest = hashlib.sha256()
                with part.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(256 * 1024), b''):
                        digest.update(chunk)
                part.replace(dest)
                meta.unlink(missing_ok=True)
                store.update(job_id, 'complete', str(dest), total, sha256=digest.hexdigest())
                return
            except Exception as exc:
                size = part.stat().st_size if part.exists() else 0
                transferred = size
                # Preserve only verified-range-capable partial files on temporary errors.
                if _transient(exc):
                    _save_partial(meta, job['url'], size, locals().get('validator', None))
                    if not meta.exists():
                        part.unlink(missing_ok=True)
                    if attempt == 0:
                        time.sleep(.75)
                        continue
                else:
                    part.unlink(missing_ok=True)
                    meta.unlink(missing_ok=True)
                raise
    except Exception as exc:
        store.update(job_id, 'failed', byte_count=transferred, error=str(exc))
