# Changelog

## v0.2 — experimental branch

**Added:** OAPEN academic open-access catalog search; SHA-256 hash recording and verification; filtered local download history; safe CSV export; failed/interrupted job retry; isolated-branch upgrade guidance.

**Fixed:** Multiple clicks or overlapping batch jobs no longer create repeated queue entries for the same source/item/format. New downloads use job-specific filenames to avoid overwriting another edition. Interrupted v0.1 jobs remain tracked during schema migration.

**Security:** Retry actions require a non-simple request header and recheck Archive file availability. Existing allowlisted download hosts, redirect validation, file-size caps, and conservative public-file checks remain in place.

**Verification:** 21 offline automated tests pass, including concurrency, migration, retries, CSV sanitization, checksums, and source parsing. This does not constitute live integration or production-readiness certification.

## v0.1 — initial local release

Initial browser-driven local ebook search and download queue with four providers and SQLite history.
