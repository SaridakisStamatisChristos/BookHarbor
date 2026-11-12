# BookHarbor v0.2 — Verified Live Integration Results

**Date:** 12 November 2026  
**Feature branch:** `feature/bookharbor-v0.2-library-upgrade`  
**Verified code commit:** `ef1ee7bc30d36ffccc04e451f4266da8f299da5e`  
**GitHub Actions run:** https://github.com/SaridakisStamatisChristos/BookHarbor/actions/runs/43285144318  
**CI outcome:** SUCCESS (with explicit source-specific caveats below).

## Offline regression tests

**30 passed**, 1 warning, in 0.70 seconds on GitHub Actions Python 3.11. Tests cover source adapters, Open Library public-scan filter, Gutenberg OPDS fallback, OAPEN OAI fallback, archive mirror validation, duplicate-safe queuing, retries, checksum verification, SQLite migration, security checks, and filename handling.

## End-to-end downloads from real providers

| Provider | Catalog test | Actual file download | Result |
|---|---|---|---|
| Project Gutenberg | 9 search results | EPUB, **189,249 bytes** | PASS: file exists, ZIP valid, SHA-256 matches |
| Internet Archive | 12 search results | TXT, **398,292 bytes** | PASS: file exists, size/hash verified |
| Standard Ebooks | 12 public feed entries | EPUB, **871,186 bytes** | PASS: ZIP valid, SHA-256 matches |
| OAPEN | 12 results using official OAI-PMH fallback | No direct EPUB/PDF URL offered by fallback | PARTIAL: metadata discovery only, download SKIPPED |
| Open Library | 0 public-access matches on the one test query | Not attempted | INCONCLUSIVE: cannot infer catalog-wide failure |

Three files were actually downloaded on GitHub's networked runner, saved through BookHarbor's SQLite job queue and downloader, validated, and automatically discarded with the temporary test directory. Results are independently inspectable in the linked CI logs and the `bookharbor-live-catalog-results` workflow artifact.

## Important caveats

- The Internet Archive mirror-selection logic passed offline tests, but the successful live TXT download **does not prove the alternate CDN path was needed**. A previous item and storage host had timed out.
- The OAPEN legacy REST search still gives HTTP 403 from the GitHub runner. A working OAI-PMH recent metadata sample allows partial discovery, but it is **not equivalent** to complete OAPEN search or direct downloads.
- Open Library's `public_scan=true` filtering now requests only openly readable items. A single query returning zero does not establish that the provider is broken.
- Upstream availability can change over time and varies by geographical network and file. No DRM or borrowing restriction bypass was added.
- Live smoke checks test a handful of sample files, **not every catalog record or downloaded file format**.

## Reproduce

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt pytest httpx
PYTHONPATH=. .venv/bin/python -m pytest -q
PYTHONPATH=. .venv/bin/python tests/live_catalog_smoke.py
```

The live test requires internet access and downloads sample ebooks temporarily.

## Promotion disposition

The feature branch demonstrates a significant improvement over v0.1 and includes automated live smoke checks. OAPEN's limited fallback and the Open Library result should remain disclosed if it is promoted. This report does **not** authorize an automatic merge. `main` is unchanged.
