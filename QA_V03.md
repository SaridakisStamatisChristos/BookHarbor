# BookHarbor v0.3 — Additional QA Results

**Test date:** 12 November 2026  
**Scope:** v0.3 Archive Explorer preview, without changing stable `main`.

## Results

| Check | Result | Evidence/limits |
|---|---|---|
| Local Python regression suite | PASS — 46 tests | Local v0.3 working-directory snapshot, Python 3.13; no network needed |
| GitHub Actions regression suite | PASS — 49 tests | [CI run 43302398924](https://github.com/SaridakisStamatisChristos/BookHarbor/actions/runs/43302398924), Python 3.11, exact tested commit `5b54bca591106c14f6948d62d740b97fd6b7cabe` |
| Local web server | PASS | Launched the application bound to 127.0.0.1:18765 in an isolated temporary data directory; GET /archive returned HTTP 200 |
| HTTP endpoints in FastAPI TestClient | PASS | GET /, /archive, /library, /static/archive.js and /api/archive/stats returned 200; unknown session returned 404 |
| Browser JavaScript smoke | PASS | Chromium rendered Archive HTML and ran `static/archive.js` with mocked API responses: search, results, inspection, individual queue action, verify-selected, and batch queue. No JavaScript exceptions |
| Mutation request guard | PASS | POST /api/archive/start without expected action header rejected with HTTP 403 |
| Live Internet Archive index | PASS with known limitation | Official Archive endpoint returned 100 records initially and 139 distinct records after a continuation fallback; no ebooks downloaded while indexing |
| Real ebook downloads | PASS, selected providers | GitHub runner downloaded valid Gutenberg EPUB (189,249 bytes), Archive TXT (398,292 bytes), and Standard Ebooks EPUB (871,186 bytes); saved files had matching SHA-256 digests |
| OAPEN direct ebooks | NOT VERIFIED | OAI metadata fallback worked; direct files were not offered |
| Open Library public search | INCONCLUSIVE | A single sample query returned no public records |

## Reproducibility and limitations

- Browser smoke used the **real** HTML and JavaScript, but **mocked** API replies to exercise UI interactions deterministically. A Chromium navigation directly to localhost was blocked by this evaluation environment's browser administrator policy, so this was not a complete networked browser-to-server E2E test.
- FastAPI routes were separately tested against the real local application server and in-process TestClient.
- The local working-directory snapshot used for the 46-test run was slightly older than the committed GitHub test suite, which ran 49 checks. The Github run is the authoritative repository CI result for its recorded commit.
- Compared with the passing CI code commit, the present feature branch adds only `ARCHIVE_V03_LIVE_VERIFICATION.md`. No runtime source code changed after that CI run.
- Internet Archive's cursor endpoint sometimes repeated a page. The fallback mode handles that case but remains capped at 10,000 results for one query. No claim of exhaustive coverage is warranted.
- Provider availability and copyright permission vary; protected or borrow-only files are not bypassed.

## Disposition

**PASS for continued local beta evaluation.** The major routes and front-end operations work under controlled tests, and selected real downloads work on the GitHub runner. **Full interactive browser-to-server validation and all-catalog download coverage remain unverified.** Preserve stable `main` until the user decides to promote v0.3.
