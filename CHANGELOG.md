# Changelog

## v0.2 provider stability patch — 12 November 2026

**Fixed:** Gutendex search failures can fall back to Gutenberg's official OPDS feed. Network-interrupted downloads restart from byte zero; validated alternate Internet Archive storage hosts are attempted only after transient CDN failures and public-file revalidation. EPUB files require valid ZIP structure. Open Library searches request public scans explicitly.

**Degraded-mode support:** When OAPEN's REST search rejects requests, an official OAI-PMH metadata sample is available. The sample is explicitly partial and cannot promise direct files or complete search coverage.

**Testing:** GitHub Actions verified **30 offline tests** and three complete networked downloads (Gutenberg EPUB, Archive TXT, Standard Ebooks EPUB). See [live run and limitations](LIVE_INTEGRATION_RESULTS.md) and [provider patch details](PROVIDER_STABILITY_V02.md).

## v0.2 — experimental branch

**Added:** OAPEN academic open-access catalog search; SHA-256 hash recording and verification; filtered local download history; safe CSV export; failed/interrupted job retry; isolated-branch upgrade guidance.

**Fixed:** Multiple clicks or overlapping batch jobs no longer create repeated queue entries for the same source/item/format. New downloads use job-specific filenames to avoid overwriting another edition. Interrupted v0.1 jobs remain tracked during schema migration.

**Security:** Retry actions require a non-simple request header and recheck Archive file availability. Existing allowlisted download hosts, redirect validation, file-size caps, and conservative public-file checks remain in place.

**Verification:** 21 offline automated tests pass, including concurrency, migration, retries, CSV sanitization, checksums, and source parsing. This does not constitute live integration or production-readiness certification.

## v0.1 — initial local release

Initial browser-driven local ebook search and download queue with four providers and SQLite history.
