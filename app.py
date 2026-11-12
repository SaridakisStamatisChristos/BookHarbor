#!/usr/bin/env python3
"""BookHarbor — local web UI, no login, no cloud backend."""
from __future__ import annotations
import csv
import hashlib
import io
import os
import secrets
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from bookharbor.downloads import run_download
from bookharbor.providers import (
    CatalogError, SOURCES, allowed_url, archive_formats, safe_identifier, preferred_format,
)
from bookharbor.storage import Store

APP_ROOT = Path(__file__).resolve().parent
HOME = Path(os.environ.get("BOOKHARBOR_HOME", str(Path.home() / ".local/share/bookharbor"))).expanduser().resolve()
LIBRARY = Path(os.environ.get("BOOKHARBOR_LIBRARY", str(HOME / "books"))).expanduser().resolve()
HOME.mkdir(parents=True, exist_ok=True)
LIBRARY.mkdir(parents=True, exist_ok=True)
KEY_FILE = HOME / "secret.key"
if not KEY_FILE.exists():
    try:
        with KEY_FILE.open("x", encoding="utf8") as fp:
            fp.write(secrets.token_urlsafe(48))
    except FileExistsError:
        pass
    try:
        KEY_FILE.chmod(0o600)
    except OSError:
        pass
SECRET = KEY_FILE.read_text(encoding="utf8").strip()
signer = URLSafeTimedSerializer(SECRET, salt="bookharbor-downloads-v1")
store = Store(HOME / "jobs.sqlite3")
download_executor = ThreadPoolExecutor(max_workers=2)

app = FastAPI(title="BookHarbor", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=str(APP_ROOT / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_ROOT / "templates"))


def mint_token(payload: dict) -> str:
    return signer.dumps(payload)


def read_token(token: str) -> dict:
    if not isinstance(token, str) or len(token) > 3000:
        raise ValueError("Invalid token")
    try:
        value = signer.loads(token, max_age=48 * 3600)
    except (BadSignature, SignatureExpired) as exc:
        raise ValueError("Expired or invalid download token; search again") from exc
    if not isinstance(value, dict):
        raise ValueError("Invalid token body")
    return value


def searchable_book(book: dict) -> dict:
    record = {k: book[k] for k in ("source", "id", "title", "author", "year", "page", "access")}
    record["download_options"] = []
    selection = {k: book[k] for k in ("source", "id", "title", "author")}
    selection["formats"] = {fmt: url for fmt, url in book.get("formats", {}).items() if allowed_url(url, book["source"])}
    record["selection_token"] = mint_token(selection)
    for extension, url in book.get("formats", {}).items():
        if not allowed_url(url, book["source"]):
            continue
        payload = {k: book[k] for k in ("source", "id", "title", "author")}
        payload.update(fmt=extension, url=url)
        record["download_options"].append({"fmt": extension.upper(), "token": mint_token(payload)})
    if book["source"] in ("archive", "openlibrary") and book["id"]:
        payload = {k: book[k] for k in ("source", "id", "title", "author")}
        record["inspect_token"] = mint_token(payload)
    return record


@app.get("/")
def index(request: Request):
    query = request.query_params.get("q", "").strip()[:120]
    source = request.query_params.get("source", "all")
    language = request.query_params.get("language", "").strip().lower()[:3]
    if source not in SOURCES and source != "all":
        source = "all"
    if language and (not language.isalpha() or len(language) not in (2, 3)):
        language = ""
    results, warnings = [], []
    if query:
        providers = list(SOURCES) if source == "all" else [source]
        with ThreadPoolExecutor(max_workers=min(4, len(providers))) as executor:
            pending = {executor.submit(SOURCES[p], query, language): p for p in providers}
            for future in as_completed(pending):
                pname = pending[future]
                try:
                    results.extend(searchable_book(book) for book in future.result())
                except Exception as exc:
                    warnings.append(f"{pname}: {str(exc)[:140]}")
        order = {name: i for i, name in enumerate(SOURCES)}
        results.sort(key=lambda book: (order[book["source"]], book["title"].casefold()))
    summary = store.summary()
    return templates.TemplateResponse(request, "index.html", {
        "query": query, "source": source, "language": language,
        "books": results, "warnings": warnings, "total": summary["completed"],
        "library": str(LIBRARY),
    })


@app.get("/api/formats")
def formats(request: Request):
    try:
        book = read_token(request.query_params.get("token", ""))
        if book.get("source") not in ("archive", "openlibrary") or not safe_identifier(book.get("id", "")):
            raise ValueError("Not an Internet Archive item")
        offers = archive_formats(book["id"])
        options = []
        for ext, url in sorted(offers.items()):
            payload = {k: book[k] for k in ("source", "id", "title", "author")}
            payload.update(fmt=ext, url=url)
            options.append({"fmt": ext.upper(), "token": mint_token(payload)})
        return {"options": options, "message": "No public EPUB/PDF/TXT/MOBI files found; this may be a lending-only item." if not options else ""}
    except (ValueError, CatalogError, KeyError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/download")
async def download(request: Request):
    if "application/json" not in request.headers.get("content-type", ""):
        return JSONResponse({"error": "JSON is required"}, status_code=415)
    try:
        raw = await request.body()
        if len(raw) > 8192:
            raise ValueError("Request too large")
        body = await request.json()
        payload = read_token(body.get("token", ""))
        source = payload.get("source")
        fmt = payload.get("fmt")
        url = payload.get("url")
        if source not in SOURCES or fmt not in ("epub", "pdf", "txt", "mobi") or not allowed_url(url, source):
            raise ValueError("Unsupported file selection")
        if source in ("archive", "openlibrary"):
            identifier = payload.get("id", "")
            # Metadata recheck: no download when rights/access changed since search.
            current = await run_in_threadpool(archive_formats, identifier)
            if current.get(fmt) != url:
                raise ValueError("That file is not currently confirmed as a public download")
        job_id, created, reason = store.add_unique(payload, fmt, url)
        if created:
            download_executor.submit(run_download, store, LIBRARY, job_id)
        return JSONResponse({"job_id": job_id, "status": "queued" if created else reason,
                             "reused": not created}, status_code=202 if created else 200)
    except (ValueError, CatalogError, KeyError, AttributeError, TypeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/batch")
async def batch(request: Request):
    """Explicitly selected books only, maximum 10 per action. No blind site crawling."""
    if "application/json" not in request.headers.get("content-type", ""):
        return JSONResponse({"error": "JSON is required"}, status_code=415)
    try:
        raw = await request.body()
        if len(raw) > 24000:
            raise ValueError("Request too large")
        body = await request.json()
        tokens = body.get("tokens", [])
        preference = str(body.get("preference", "auto"))
        if not isinstance(tokens, list) or not (1 <= len(tokens) <= 10):
            raise ValueError("Select 1 to 10 books per batch")
        if preference not in ("auto", "epub", "pdf", "mobi", "txt"):
            raise ValueError("Unsupported format preference")
        queue, skipped = [], []
        for token in tokens:
            try:
                book = read_token(token)
                source = book.get("source")
                if source not in SOURCES:
                    raise ValueError("Unknown catalog")
                formats_found = book.get("formats") or {}
                if source in ("archive", "openlibrary"):
                    if not safe_identifier(book.get("id", "")):
                        raise ValueError("No public Archive identifier")
                    formats_found = await run_in_threadpool(archive_formats, book["id"])
                choice = preferred_format(formats_found, preference)
                if not choice:
                    raise ValueError("No open files found")
                fmt, url = choice
                if not allowed_url(url, source):
                    raise ValueError("Unexpected download host")
                job_id, created, reason = store.add_unique(book, fmt, url)
                if created:
                    download_executor.submit(run_download, store, LIBRARY, job_id)
                    queue.append(job_id)
                else:
                    skipped.append(f"Already {reason}: {book.get('title', 'Book')}")
            except (ValueError, CatalogError, KeyError, TypeError) as exc:
                skipped.append(str(exc)[:150])
        return JSONResponse({"queued": queue, "skipped": skipped}, status_code=202)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.get("/api/jobs")
def jobs_api():
    rows = store.list(limit=100)
    safe_rows = [{k: item[k] for k in ("id", "title", "author", "source", "format", "status", "byte_count", "error", "created_at")}
                 for item in rows]
    return {"jobs": safe_rows}


@app.get("/library")
def library_page(request: Request):
    query = request.query_params.get('q', '').strip()[:120]
    status = request.query_params.get('status', 'all')
    if status not in ('all', 'queued', 'running', 'complete', 'failed', 'interrupted'):
        status = 'all'
    return templates.TemplateResponse(request, "library.html", {
        "jobs": store.list_filtered(query, status, limit=200),
        "folder": str(LIBRARY), "query": query, "status": status,
        "summary": store.summary()
    })


def _safe_csv_cell(value) -> str:
    """Prevent CSV formulas from executing when opened in spreadsheet software."""
    data = str(value if value is not None else '')
    return "'" + data if data.lstrip().startswith(('=', '+', '-', '@')) else data


@app.get('/library/export.csv')
def export_csv(request: Request):
    query = request.query_params.get('q', '').strip()[:120]
    status = request.query_params.get('status', 'all')
    if status not in ('all', 'queued', 'running', 'complete', 'failed', 'interrupted'):
        status = 'all'
    rows = store.list_filtered(query, status, limit=10000)
    output = io.StringIO()
    writer = csv.writer(output)
    columns = ('id', 'title', 'author', 'source', 'book_id', 'format', 'status',
               'byte_count', 'sha256', 'created_at', 'updated_at', 'error')
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_safe_csv_cell(row.get(col)) for col in columns])
    return Response(output.getvalue(), media_type='text/csv; charset=utf-8', headers={
        'Content-Disposition': 'attachment; filename="bookharbor-library.csv"',
        'Cache-Control': 'no-store'
    })


@app.get('/api/verify/{job_id}')
def verify_download(job_id: int):
    job = store.get(job_id)
    if not job or job['status'] != 'complete':
        raise HTTPException(status_code=404, detail='Not a completed download')
    target = Path(job['path']).resolve()
    if not target.is_relative_to(LIBRARY) or not target.is_file():
        return {'status': 'missing', 'job_id': job_id}
    if not job.get('sha256'):
        return {'status': 'untracked', 'job_id': job_id,
                'message': 'Legacy download: checksum not recorded in v0.1.'}
    digest = hashlib.sha256()
    with target.open('rb') as f:
        for block in iter(lambda: f.read(256 * 1024), b''):
            digest.update(block)
    return {'status': 'verified' if digest.hexdigest() == job['sha256'] else 'mismatch',
            'job_id': job_id}


@app.post('/api/retry/{job_id}')
async def retry_download(job_id: int, request: Request):
    """Retry a failed or interrupted job, without bypassing Archive checks."""
    # A non-simple custom header prevents cross-origin HTML forms from triggering jobs.
    if request.headers.get('x-bookharbor-action') != 'retry':
        return JSONResponse({'error': 'Retry requires a local app request'}, status_code=403)
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404)
    if job['status'] not in ('failed', 'interrupted'):
        return JSONResponse({'error': 'Only failed/interrupted jobs can be retried'}, status_code=409)
    src, fmt, url = job['source'], job['format'], job['url']
    if src not in SOURCES or fmt not in ('epub', 'pdf', 'txt', 'mobi') or not allowed_url(url, src):
        return JSONResponse({'error': 'Unsafe or unsupported original download'}, status_code=400)
    if src in ('archive', 'openlibrary'):
        try:
            now = await run_in_threadpool(archive_formats, job['book_id'])
            if now.get(fmt) != url:
                raise ValueError('No longer confirmed as an open Archive file')
        except (CatalogError, ValueError) as exc:
            return JSONResponse({'error': str(exc)}, status_code=400)
    book = {'source': src, 'id': job['book_id'], 'title': job['title'], 'author': job['author']}
    new_id, created, reason = store.add_unique(book, fmt, url)
    if created:
        download_executor.submit(run_download, store, LIBRARY, new_id)
    return JSONResponse({'job_id': new_id, 'reused': not created,
                         'status': 'queued' if created else reason}, status_code=202 if created else 200)



@app.get("/file/{job_id}")
def local_file(job_id: int):
    row = store.get(job_id)
    if not row or row["status"] != "complete":
        raise HTTPException(status_code=404)
    file_path = Path(row["path"]).resolve()
    if not file_path.is_relative_to(LIBRARY) or not file_path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(file_path, filename=file_path.name)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("BOOKHARBOR_PORT", "8765"))
    print(f"BookHarbor at http://127.0.0.1:{port} | library: {LIBRARY}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
