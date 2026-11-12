# Provider Stability Patch — v0.2 Experimental Branch

Updated: 12 November 2026. **Only the feature branch is modified.** No automatic promotion to `main`.

## Improvements

- **Gutenberg:** Gutendex remains the normal JSON catalog. On transient failure or a blocked response, switch to Project Gutenberg's officially published OPDS 1 Atom catalog; consume only identified open acquisition links from `gutenberg.org`. Gutenberg plans to retire XML OPDS in 2027; this fallback will require a future update.
- **Internet Archive:** One retry from byte zero for temporary network/server errors. When public-file metadata explicitly approves the requested file, the downloader may also attempt the two official redundant Archive storage nodes (`d1` and `d2`) if the canonical download host stalls. All redirects and hosts remain allowlisted and checked. The public-file recheck is required before using the alternates.
- **OAPEN:** The public REST search returned HTTP 403 from GitHub Actions. If unavailable, BookHarbor reads a bounded *recent-record sample* (up to 300 entries per process) through OAPEN's official OAI-PMH metadata API. OAI-PMH is a harvesting service, not a full-text search API: **this is not a complete OAPEN search and does not guarantee direct PDF/EPUB links.** Available item pages are shown, with no fabricated file URLs.
- **Open Library:** Query explicitly for `public_scan=true` before locally enforcing `ebook_access=public`. Borrowable and restricted records remain excluded.
- **Integrity:** Validate EPUB ZIP structure, preserve clean retries, reject HTML/JSON error pages and incomplete downloads, and retain SHA-256 verification.

## Live evidence

Earlier GitHub Actions smoke runs demonstrated a valid download from Standard Ebooks (871,186 bytes) and, after the OPDS/catalog improvements, a Gutenberg EPUB (189,249 bytes). The Archive test previously failed with a data-node timeout. Additional CI results are recorded in the feature branch's GitHub Actions tab.

The live integration suite is **not guaranteed green** when third-party providers reject requests, time out, or give no public downloadable file. Do not interpret an unavailable source as proof of a code regression, but likewise do not claim an untested provider is fully working.

## Run the tests

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt pytest httpx
PYTHONPATH=. .venv/bin/python -m pytest -q
PYTHONPATH=. .venv/bin/python tests/live_catalog_smoke.py
```

The second command makes **real outbound requests** and downloads bounded sample ebooks, then removes them after validation. It may fail due to source availability.

## Safety and restrictions

No DRM, subscription, lending, or authentication bypasses. Never treat Project Gutenberg's US publication rights as automatic permission in another country. Do not change the local-only HTTP server binding to a public address without authentication. Use the providers' official permitted interfaces and respect rate limits. Archive mirrors are used only when the same open item is explicitly approved by the Archive metadata API.

## Merge gate

Consider promotion only after the branch's exact current commit passes offline tests, at least Gutenberg and Standard Ebooks successfully perform end-to-end downloads, and the residual Archive/OAPEN limitations are accepted and documented. A source-specific outage is not equivalent to a verified fix.