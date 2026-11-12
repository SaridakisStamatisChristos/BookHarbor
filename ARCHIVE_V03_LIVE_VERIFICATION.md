# BookHarbor v0.3 — Live Verification Record

**Date:** 12 November 2026  
**Code commit tested:** `5b54bca591106c14f6948d62d740b97fd6b7cabe`  
**GitHub Actions run:** https://github.com/SaridakisStamatisChristos/BookHarbor/actions/runs/43302398924  
**Branch:** `feature/bookharbor-v0.3-archive-explorer`  
**Status:** CI PASS, with provider limitations below.

## Offline checks

- **49 tests passed**, **1 warning** under GitHub Actions Python 3.11.
- Tests cover existing v0.2 features, migration compatibility, archive filter sanitization, session persistence, index deduplication, bounded background harvesting, stop controls, signed API actions, download resume, strict HTTP Content-Range validation, and archive mirror fallback.
- The tests use mocked responses for negative and edge cases.

## Live network validation

- Existing catalog/download smoke tests: **9 checks, no reported failures**. Previously verified providers include Gutenberg, Internet Archive and Standard Ebooks. OAPEN's direct ebook access remains limited and Open Library's sample query is inconclusive.
- New Archive Explorer: **100 real item records** indexed on first cursor page, **139 unique records after continuation**. Source mode switched to **Advanced Search fallback** when the scrape service repeated its cursor. Live continuation passed.
- No mass ebook downloads were performed during indexing. The live search test used a temporary SQLite catalog and deleted it after completion.

## Caveats

- Internet Archive's cursor scrape API can return a cached first page again on continuation. This was independently observed in the live diagnostic probe. The app detects a repeated cursor and falls back to the official sorted Advanced Search API.
- Sorted Advanced Search has a **10,000-result limit per query**. The app does not claim unlimited deep pagination on a provider whose cursor endpoint is currently replaying records.
- Metadata indexing does not imply an ebook is downloadable, license-cleared, or in the public domain in Greece. Public formats are inspected separately, with rights restrictions left intact.
- Background index batches are user-started, limited to 50 pages/5,000 metadata items per batch, and stop when the app shuts down.

## Disposition

**Preview branch is ready for local testing.** This evidence does **not** automatically authorize promotion to `main`; the stable v0.2 branch remains unchanged until the user requests promotion.

See [Archive Explorer guide](ARCHIVE_EXPLORER_V03.md).
