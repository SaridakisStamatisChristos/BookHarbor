# BookHarbor v0.3 — Internet Archive Explorer

**Status:** feature-branch preview; `main` remains the stable v0.2 release until merge.

## What changed

Internet Archive has millions of digitized texts, but ordinary search pagination does not cover the complete catalog. BookHarbor v0.3 adds a dedicated **Archive Explorer** using Internet Archive's official read-only cursor API (`/services/search/v1/scrape`). This is **metadata exploration**, not a mass downloader.

The new local database `~/.local/share/bookharbor/archive_catalog.sqlite3` stores discovered titles and search sessions independently of the existing download history (`jobs.sqlite3`). A stopped or restarted BookHarbor can reopen a session link and continue indexing where it left off, provided Internet Archive still accepts the saved cursor. Archive results are not guaranteed immutable: the provider may change its index or availability between visits.

### How to use

1. Install from the **feature branch** and launch normally with `./run.sh`.
2. Open `http://127.0.0.1:8765/archive` (or click **Archive Explorer** in the navigation).
3. Enter a title/subject search, an author, or a specific collection identifier. Optional filters: language (`en`, `el`), subject, publication years.
4. Click **Search and index first 100**. Each later **Index next 100** click requests exactly one additional catalog page. This approach can move past ordinary search pagination limits.
5. Browse your saved results; use local title/author/subject search and availability filters.
6. Click **Inspect open files** on a title to check that item's current public EPUB/PDF/TXT/MOBI metadata. Only files marked public and matching the existing allowlist are offered.
7. Select up to **5** titles to check file availability together, or select up to **10** to request individually verified downloads in one batch. The existing downloader independently rechecks Archive metadata before enqueueing.
8. Find completed ebooks under **My Library**; no books are downloaded while indexing.

### Important distinctions

- **Indexed** means an Internet Archive *metadata record*, not a downloaded or freely licensed book.
- **Verified public file** means Internet Archive's item metadata offered at least one accessible supported file at the time checked. The file can later become unavailable.
- **Unavailable** means no supported public files were returned; it does **not** necessarily mean the entire item is unavailable for reading or borrowing.
- **Unchecked** means BookHarbor has not checked the item's file metadata.
- Public download availability and copyright permission are separate questions, particularly outside the United States.

### Resource limits and safeguards

- Exactly **one 100-record page per explicit request**. No background mass crawling.
- Up to **50,000 indexed results per search session**. Start a new narrower session for additional exploration.
- At least **1 second between cursor page requests** in the running app. Provider throttling and changes are respected, not bypassed.
- Metadata de-duplicated by Internet Archive identifier.
- No automatic file downloads; existing 350 MiB per-file cap, two-worker queue, allowlist and tokenized actions remain in force.
- Unsupported, encrypted, private, lending-only and restricted ebook files are excluded; no DRM bypass.
- Download resume is allowed only with a strong ETag or Last-Modified `If-Range` validator; if a server ignores Range, BookHarbor safely restarts instead of appending incompatible bytes.
- File verification includes basic format signatures, a readable EPUB ZIP and a SHA-256 hash of the final saved file.

### Configuration

No additional packages or API keys are required beyond existing `requirements.txt`. The Archive Explorer database follows `BOOKHARBOR_HOME`. The download directory follows `BOOKHARBOR_LIBRARY`.

### Testing

Run local offline checks from the root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt pytest httpx
PYTHONPATH=. .venv/bin/python -m pytest -q
```

Optional live metadata check (makes two real requests to Internet Archive):

```bash
PYTHONPATH=. .venv/bin/python tests/live_archive_explorer_smoke.py
```

### Limitations

- Indexed metadata is not a complete cross-edition union of all books. Some searches may include false positives because Internet Archive's metadata and indexing evolve.
- Access filtering is based on **previously inspected** items. It is not a claim to search all the Archive's public files without contacting their individual metadata endpoints.
- Internet Archive search cursors can expire or become invalid; the session retains a last error and can be restarted as a new search if necessary.
- The download queue is still user-initiated, maximum 10 titles per batch. It does not indiscriminately retrieve thousands of files.
- Open Library and OAPEN integrations are unchanged in this feature; their known limitations remain disclosed.

API reference: [Internet Archive Item Search APIs](https://archive.org/services/docs/api/item-search.html).
