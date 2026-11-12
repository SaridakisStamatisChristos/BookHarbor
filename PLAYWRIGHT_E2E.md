# Playwright end-to-end tests for BookHarbor

The `tests/test_playwright_e2e.py` suite starts the **real FastAPI app on a random localhost port** and drives it with **headless Chromium**. Requests to `/archive`, `/api/archive/*`, `/api/download`, `/api/batch` and `/library` are made through the browser and handled by the actual BookHarbor application.

The tests keep all files inside a temporary directory and never read or modify your personal library.

## Coverage

- Browser loads the Archive Explorer and submits a search to the running server.
- Real SQLite search session stores indexed books and survives a reload.
- Browsing and filtering indexed results, including rejecting unsafe catalog HTML.
- No download occurs during metadata-only discovery.
- Restricted books do not expose a public file download button.
- Public file inspection reveals an eligible format.
- An individual download is queued via real HTTP; the actual downloader stores the file and its SHA-256 matches.
- The multi-book batch action queues another real job and updates Explorer's verified-file tally.
- The My Library page displays completed downloads.
- Browser JavaScript errors fail the test.
- Failure artifacts contain a screenshot and Playwright trace.

**Testing boundary:** Internet Archive discovery replies, Archive public-file metadata and external ebook bytes are **deterministic test fixtures**. BookHarbor's UI, server routes, download queue, filesystem writes and SQLite databases are **not mocked**. Separate GitHub live-smoke workflows test real external providers.

## Run locally on Linux Mint or Ubuntu

From the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-e2e.txt
python -m playwright install --with-deps chromium
PYTHONPATH=. python -m pytest tests/test_playwright_e2e.py -q
```

For a preinstalled local Chromium rather than Playwright's bundled binary:

```bash
BOOKHARBOR_CHROMIUM_PATH=/usr/bin/chromium PYTHONPATH=. python -m pytest tests/test_playwright_e2e.py -q
```

If a hosted browser environment explicitly blocks localhost with `ERR_BLOCKED_BY_ADMINISTRATOR`, run the tests on GitHub Actions or a local machine without that browser restriction.

## GitHub Actions

`.github/workflows/browser-e2e.yml` runs the tests on **Ubuntu 24.04** with Python 3.11 and Playwright 1.57.0. It runs for pushes to the v0.3 feature branch and `main`, pull requests targeting `main`, and can be started manually through the Actions tab.

If tests fail, download `bookharbor-playwright-failures` from that workflow run. Use:

```bash
python -m playwright show-trace bookharbor-failed-trace.zip
```

To inspect actions, DOM snapshots and screenshots.

Browser E2E checks do not certify every upstream provider, arbitrary-size Archive searches, or that all downloaded titles are legally usable. All access restrictions remain in force.
