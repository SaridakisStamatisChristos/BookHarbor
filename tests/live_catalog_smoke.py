"""Optional LIVE integration smoke test; makes real provider requests and downloads.

Unlike the ordinary pytest suite, run this only when network access is available.
Each check is bounded and downloaded samples are deleted after verification.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

from bookharbor import downloads, providers
from bookharbor.storage import Store

# Keep smoke downloads small. The app's production limit is unchanged.
downloads.MAX_FILE_BYTES = 25 * 1024 * 1024

REPORT = []


def record(source: str, stage: str, state: str, message: str = "", **data):
    row = {"source": source, "stage": stage, "state": state, "message": message, **data}
    REPORT.append(row)
    print(f"[{state}] {source} / {stage}: {message}", flush=True)


def find_offer(records, allowed=("epub", "txt", "pdf")):
    for book in records:
        for kind in allowed:
            if book.get("formats", {}).get(kind):
                return book, kind, book["formats"][kind]
    return None


def actual_download(book: dict, kind: str, url: str, temp: Path):
    """Exercise the real SQLite -> downloader -> saved-file flow."""
    source = book["source"]
    store = Store(temp / f"{source}.sqlite")
    job_id, created, _ = store.add_unique(book, kind, url)
    assert created, "Expected a new queue entry"
    downloads.run_download(store, temp / "ebooks", job_id)
    result = store.get(job_id)
    assert result, "Download job not found"
    if result["status"] != "complete":
        raise RuntimeError(f"Download status={result['status']}, error={result['error']}")
    path = Path(result["path"])
    assert path.exists() and path.is_file(), "Downloaded file missing"
    assert path.stat().st_size == result["byte_count"] > 100
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == result["sha256"], "SHA-256 mismatch"
    if kind == "pdf":
        assert path.read_bytes()[:5] == b"%PDF-", "Not a PDF"
    if kind == "epub":
        import zipfile
        assert zipfile.is_zipfile(path), "Not a valid EPUB ZIP"
    size = path.stat().st_size
    record(source, "download", "PASS", f"Saved valid {kind} ({size} bytes, SHA-256 matches)",
           format=kind, size_bytes=size, sha256=actual, catalog_id=book["id"])


def main() -> int:
    failures = []
    with tempfile.TemporaryDirectory(prefix="bookharbor-live-") as directory:
        temp = Path(directory)

        # Gutenberg: search result -> direct book download.
        try:
            books = providers.search_gutenberg("Alice Adventures Wonderland", "en", limit=12)
            record("gutenberg", "search", "PASS" if books else "FAIL", f"{len(books)} results")
            offer = find_offer(books, ("epub", "txt"))
            if not offer:
                raise RuntimeError("No downloadable EPUB or TXT from Gutenberg search")
            actual_download(*offer, temp)
        except Exception as exc:
            record("gutenberg", "integration", "FAIL", repr(exc))
            failures.append("gutenberg")

        # Internet Archive: search -> inspect public file metadata -> download.
        try:
            books = providers.search_archive("Alice Adventures Wonderland", "en", limit=12)
            record("archive", "search", "PASS" if books else "WARN", f"{len(books)} results")
            offer = None
            for book in books[:6]:
                try:
                    formats = providers.archive_formats(book["id"])
                    book["formats"] = formats
                    offer = find_offer([book], ("epub", "txt"))
                    if offer:
                        break
                except providers.CatalogError:
                    continue
            if offer:
                actual_download(*offer, temp)
            else:
                record("archive", "download", "SKIP",
                       "First six search items had no accessible EPUB/TXT; no bypass attempted")
        except Exception as exc:
            record("archive", "integration", "FAIL", repr(exc))
            failures.append("archive")

        # Open Library: discovery check; its actual files use the Archive downloader.
        try:
            books = providers.search_openlibrary("Alice Adventures Wonderland", "en", limit=12)
            record("openlibrary", "search", "PASS" if books else "WARN",
                   f"{len(books)} public-access results")
        except Exception as exc:
            record("openlibrary", "search", "FAIL", repr(exc))
            failures.append("openlibrary")

        # OAPEN: academic catalog -> PDF/EPUB, preserving source URL allowlist.
        try:
            books = providers.search_oapen("philosophy", "en", limit=12)
            record("oapen", "search", "PASS" if books else "FAIL", f"{len(books)} results")
            offer = find_offer(books, ("epub", "pdf"))
            if not offer:
                raise RuntimeError("OAPEN returned no direct EPUB or PDF files")
            actual_download(*offer, temp)
        except Exception as exc:
            record("oapen", "integration", "FAIL", repr(exc))
            failures.append("oapen")

        # Recent feed is not a full search index; check a known public feed request.
        try:
            books = providers.search_standard("", "en", limit=12)
            record("standard", "feed", "PASS" if books else "WARN",
                   f"{len(books)} recent-release feed entries")
        except Exception as exc:
            record("standard", "feed", "FAIL", repr(exc))
            failures.append("standard")

    Path("live_smoke_report.json").write_text(
        json.dumps({"results": REPORT, "failures": failures}, indent=2), encoding="utf-8")
    print("\nLIVE SMOKE SUMMARY", json.dumps({"failures": failures, "checks": len(REPORT)}), flush=True)
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
