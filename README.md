# BookHarbor v0.3 — Local Ebook Discovery & Download Manager

**BookHarbor** is a free, open-source application that runs on your own computer. Use your web browser to discover legally accessible ebooks, explore Internet Archive metadata in depth, download supported public files, and manage your local library.

**Current release in `main`: v0.3.** No account, cloud server, API key, Docker or Playwright is required to use the application. Internet access is required to search remote catalogs and download books.

[Quick start](#quick-start-linux-mint--ubuntu) · [Archive Explorer](#internet-archive-explorer-v03) · [Other platforms](#windows-10--11) · [Configuration and storage](#configuration--storage) · [Tests](#optional-development-and-testing) · [Troubleshooting](#troubleshooting)

> **Beta software:** Internet Archive search results can include borrow-only or restricted items. Indexed metadata is not an offer of a public download, and access to a file does not necessarily establish the right to use it in your country. BookHarbor does not bypass logins, lending rules, DRM or other source restrictions.

## What BookHarbor offers

- **Five catalog integrations:** Project Gutenberg, Internet Archive, Open Library, Standard Ebooks' public recent-release feed, and OAPEN academic metadata.
- **Internet Archive Explorer:** Advanced author, title, subject, collection, language and year filters; persistent local indexing; per-page or bounded background indexing.
- **Explicit file checks:** Inspect individual Internet Archive records for supported public EPUB, PDF, TXT or MOBI files before downloading.
- **Managed download queue:** Two simultaneous workers, up to 10 explicitly selected titles per batch, duplicate handling, safe file naming, bounded file size, and eligible HTTP Range resumption.
- **Local library:** Search and filter your download history, retry failed jobs, verify new files against SHA-256 checksums, and export metadata to CSV.
- **Automated quality checks:** Python regression tests, Chromium/Playwright browser tests in GitHub Actions, and separate live-provider smoke tests.

The app runs only on `127.0.0.1` by default. It is not a hosted or multi-user service.

## Requirements

- **Python 3.10 or newer** (Python 3.11 is a good choice).
- Linux Mint, Ubuntu, Debian, Windows 10/11 or macOS.
- A modern browser (Firefox, Chrome, Chromium, Safari or Edge).
- Internet access for initial Python dependencies, catalog search and file downloads.
- Disk space for your books. Individual downloads are capped at **350 MiB**.
- **Git** for the recommended installation/update method; not necessary if using the repository's **Code → Download ZIP** option.

The normal runtime dependencies are listed in [`requirements.txt`](requirements.txt). **Chromium and Playwright are optional developer/test dependencies, not required for everyday ebook use.**

## Quick start: Linux Mint / Ubuntu

Open **Terminal** and run:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip

git clone https://github.com/SaridakisStamatisChristos/BookHarbor.git
cd BookHarbor
./run.sh
```

The first launch creates a local `.venv` and installs the Python packages automatically. Keep the terminal open while using the app.

Open these addresses in your browser:

| Screen | Address |
|---|---|
| **Discover** (search all providers) | http://127.0.0.1:8765/ |
| **Internet Archive Explorer** | http://127.0.0.1:8765/archive |
| **My Library** | http://127.0.0.1:8765/library |

**Stop:** Press **Ctrl+C** in the terminal. **Restart:** Open a terminal in the BookHarbor folder and run `./run.sh` again.

If `./run.sh` says *Permission denied*, use `bash run.sh` or `chmod +x run.sh` once.

### Already have BookHarbor v0.1 or v0.2?

Keep your current library; **do not delete your ebook or state directories**. Stop the running app and back up your state directory before updating. For the default Linux configuration:

```bash
# Stop BookHarbor first (Ctrl+C in its terminal).
cp -a "$HOME/.local/share/bookharbor" "$HOME/.local/share/bookharbor.backup"
cd ~/BookHarbor
git switch main
git pull --ff-only
./run.sh
```

The backup command assumes the directory already exists and BookHarbor was cloned in `~/BookHarbor`. Change the paths if you installed it elsewhere or configured `BOOKHARBOR_HOME`. A fresh install already on `main` only needs `git pull --ff-only` to update.

The v0.3 schema adds an Archive metadata database alongside the existing download history. Keep your existing library and history; do not run two BookHarbor versions against the same state directory simultaneously.

## Windows 10 / 11

1. Install **Python 3.10+** from https://www.python.org/downloads/windows/ and enable **Add Python to PATH** if offered.
2. Install **Git for Windows** from https://git-scm.com/downloads/win, or download and extract the source ZIP from GitHub.
3. Open **PowerShell** in the folder containing `app.py` and `requirements.txt`:

```powershell
git clone https://github.com/SaridakisStamatisChristos/BookHarbor.git
cd BookHarbor
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

If you downloaded a ZIP instead of cloning, skip the `git clone` command and enter the extracted repository folder.

Open http://127.0.0.1:8765 in your browser. Stop with **Ctrl+C**. For later starts, run `.\.venv\Scripts\python.exe app.py` from the same folder. The shell script `run.sh` is intended for Linux/macOS, not PowerShell.

To update a Git checkout: stop the app, back up `BOOKHARBOR_HOME` (see below), run `git pull --ff-only` in the repository, then reinstall dependencies if needed using the `pip install -r requirements.txt` command above.

## macOS

Install Python 3.10+ and Git first. If you use Homebrew, `brew install python git` is one option.

```bash
git clone https://github.com/SaridakisStamatisChristos/BookHarbor.git
cd BookHarbor
bash run.sh
```

Open http://127.0.0.1:8765. Stop with **Ctrl+C**.

Alternatively, use `python3 -m venv .venv`, then `. .venv/bin/activate`, `python -m pip install -r requirements.txt`, and `python app.py`.

## Using the Discover screen

1. Open the homepage and search for a **book title, author, or subject** (for example, `Euclid` or `geometry`).
2. Choose one catalog or **All sources**; optionally enter a short language code such as `en` or `el`.
3. Some results show a direct **EPUB / PDF / TXT / MOBI** download option. Other results offer **Find files**, which checks the provider's public file metadata.
4. Select individual books and click **Download selected** to queue **up to 10 titles per action**. Choose a preferred format, or leave **Auto (EPUB first)**.
5. Open **My Library** to check completed, queued, interrupted or failed jobs. Use **Verify file** to recheck a recorded checksum or **Retry** for failed/interrupted jobs.

The homepage shows a **small preview** from each catalog; use **Archive Explorer** for deeper Internet Archive metadata discovery.

## Internet Archive Explorer (v0.3)

Go to **http://127.0.0.1:8765/archive** or use **Archive Explorer** in the top navigation.

### Search and index

1. Fill in any relevant combination of **title/search terms**, **author**, **subject**, **collection identifier**, **language**, and **publication year range**. Example: subject `mathematics` and collection `americana`.
2. Click **Search and index first 100**. The first page is saved to a local SQLite index; **this does not download books**.
3. Click **Index next 100 records** for another page. Or set **Pages per batch** (1–50) and click **Index batch in background** to request up to **5,000 metadata records**. Use **Stop batch** to stop after the current request completes.
4. Search or filter **your locally indexed results**. Availability filters distinguish **unchecked**, **verified public file**, and **no supported public file**.
5. A saved session can be revisited from its `/archive?session=...` URL; retain/bookmark the URL to continue indexing later.
6. Click **Inspect open files** on a record, or select **up to 5** records and click **Check public files for up to 5 selected**.
7. Select **up to 10** verified or inspectable titles, choose your format preference and click **Download up to 10 selected**. BookHarbor rechecks eligible Archive file metadata when queueing.
8. Go to **My Library** to see downloads and their integrity status.

**Limits and important details:**

- Up to **50,000 indexed metadata records per search session**; start narrower sessions for other slices.
- Internet Archive's cursor service can replay a page. BookHarbor detects this and falls back to Advanced Search, which has a **10,000-result ceiling per query**. It therefore cannot guarantee exhaustive coverage of millions of records from one search.
- **Indexed** ≠ downloaded; **public file detected** ≠ copyright-cleared. Borrow-only, private, restricted or DRM-protected files are excluded.
- Background indexing is deliberately bounded and does not continue after the app closes. No automatic mass-download of indexed titles is performed.

See the more detailed [Archive Explorer reference](ARCHIVE_EXPLORER_V03.md) and [live verification report](ARCHIVE_V03_LIVE_VERIFICATION.md). Older references to a *feature-branch preview* in historical milestone documents predate the v0.3 merge: **v0.3 is now on `main`**.

## Managing downloaded books

In **My Library** (http://127.0.0.1:8765/library), you can:

- Find books by title/author/catalog and filter download status.
- Open completed files or check **Verify file** (compares against SHA-256 stored when the file was downloaded).
- Retry failed or interrupted transfers; some partial files can resume when the remote server provides a valid HTTP validator and range response.
- Select **Export matching CSV** to save a spreadsheet-friendly **metadata report**, not the ebook files themselves.

Legacy v0.1 downloads may have no recorded checksum and are shown as **untracked**. A file being hash-verified means its bytes match BookHarbor's recorded hash; it does **not** independently prove the file is authentic or rights-cleared.

For extensive book organization or format conversion, consider a separate tool such as [Calibre](https://calibre-ebook.com/).

## Configuration & storage

By default BookHarbor uses these locations, relative to your user home directory (including on Windows):

| What | Default |
|---|---|
| Ebook files | `~/.local/share/bookharbor/books/` |
| Download/job history | `~/.local/share/bookharbor/jobs.sqlite3` |
| Internet Archive search/index sessions | `~/.local/share/bookharbor/archive_catalog.sqlite3` |
| Local action-signing secret | `~/.local/share/bookharbor/secret.key` |
| Web server | `127.0.0.1:8765` |

Configure before starting the app:

| Variable | Purpose |
|---|---|
| `BOOKHARBOR_HOME` | State, SQLite databases and signing secret |
| `BOOKHARBOR_LIBRARY` | Where downloaded ebook files are stored |
| `BOOKHARBOR_PORT` | Port of the local web server (default `8765`) |
| `BOOKHARBOR_CONTACT` | Contact URL/email included in catalog requests' User-Agent |

For example, on Linux Mint:

```bash
mkdir -p "$HOME/Books/BookHarbor"
export BOOKHARBOR_HOME="$HOME/.local/share/bookharbor"
export BOOKHARBOR_LIBRARY="$HOME/Books/BookHarbor"
export BOOKHARBOR_PORT=8765
./run.sh
```

Or change only the port for one launch:

```bash
BOOKHARBOR_PORT=8766 ./run.sh
```

Then visit http://127.0.0.1:8766.

On Windows PowerShell, set variables before `python.exe app.py`, e.g. `$env:BOOKHARBOR_PORT = "8766"`.

**Backups:** Stop the app, then copy both your **`BOOKHARBOR_HOME`** directory (databases and signing secret) and **`BOOKHARBOR_LIBRARY`** directory (book files) if you customized their locations. By default, the book folder is already inside `BOOKHARBOR_HOME`. Do not publish the signing secret or private database contents.

## Updating, upgrading and uninstalling

**Update from GitHub:** Stop the app; from its source folder run `git switch main` and `git pull --ff-only`, then restart it using the instructions for your OS. Do not discard local edits without reviewing them.

**Using a ZIP instead of Git:** On the [repository homepage](https://github.com/SaridakisStamatisChristos/BookHarbor), choose **Code → Download ZIP**, extract the source and follow your platform's Python commands. The legacy [v0.1 release archive](releases/BookHarbor_v0_1_Linux_Windows.zip) is **not** the current v0.3 source. ZIP installations cannot use `git pull`; obtain a newer ZIP for upgrades.

**Uninstall:** Stop BookHarbor and delete the application source folder and its `.venv` if desired. Your ebook and database directories are separate and **will remain** until you explicitly remove them. Back up your books before deleting anything.

## Optional development and testing

**You do not need Playwright to use BookHarbor.** It is retained in the repository so future changes can be checked automatically. The default `./run.sh` installs only `requirements.txt`.

### Python tests (offline)

```bash
cd BookHarbor
.venv/bin/python -m pip install pytest httpx
PYTHONPATH=. .venv/bin/python -m pytest -q --ignore=tests/test_playwright_e2e.py
```

On Windows, use `.\.venv\Scripts\python.exe -m pip install pytest httpx` and `.\.venv\Scripts\python.exe -m pytest -q --ignore=tests/test_playwright_e2e.py`.

### Playwright browser tests (optional, Linux Mint/Ubuntu)

```bash
cd BookHarbor
.venv/bin/python -m pip install -r requirements-e2e.txt
.venv/bin/python -m playwright install --with-deps chromium
PYTHONPATH=. .venv/bin/python -m pytest tests/test_playwright_e2e.py -q
```

The browser suite starts an isolated local app and uses temporary data. It exercises the real UI, FastAPI server, SQLite database and download queue, with **external catalog HTTP responses replaced by test fixtures**. It does not download live Archive files. See [PLAYWRIGHT_E2E.md](PLAYWRIGHT_E2E.md).

### Live provider tests (optional; network required)

```bash
cd BookHarbor
PYTHONPATH=. .venv/bin/python tests/live_catalog_smoke.py
PYTHONPATH=. .venv/bin/python tests/live_archive_explorer_smoke.py
```

These make real requests to upstream services and can fail if a catalog throttles requests or is unavailable. The ebook smoke test temporarily downloads selected small files. Don't run this repeatedly or at scale.

GitHub Actions also runs the [Chromium browser workflow](.github/workflows/browser-e2e.yml) on pushes to `main` and the [live catalog workflow](.github/workflows/live-catalog-smoke.yml) in its configured branches or manually. Historical verified results: **49 offline regression checks and a passing Chromium E2E run**, plus live ebook downloads from **Gutenberg, Internet Archive and Standard Ebooks**. See [Playwright QA](QA_V03.md), [live Archive verification](ARCHIVE_V03_LIVE_VERIFICATION.md) and [provider live-download evidence](LIVE_INTEGRATION_RESULTS.md). These are point-in-time results, not a guarantee that providers are currently online.

## Troubleshooting

| Problem | What to try |
|---|---|
| `python3: command not found` | Install Python 3.10+ and reopen the terminal. On Windows, use `py` or your full Python executable path. |
| `No module named venv` / environment creation fails | Install `python3-venv` on Ubuntu/Mint, then rerun `./run.sh`. |
| `./run.sh: Permission denied` | Run `bash run.sh` or `chmod +x run.sh`. |
| Browser page will not open | Ensure the terminal app process is still running; open `http://127.0.0.1:8765` on the **same computer**. |
| Port already in use | Run `BOOKHARBOR_PORT=8766 ./run.sh` (Linux/macOS) or set the variable in PowerShell, then use port 8766 in the browser. |
| Catalog search fails or times out | Check internet access, try one provider, reduce query complexity and retry later. Remote catalogs can reject or rate-limit requests. |
| Internet Archive cursor repeats / pagination stops | BookHarbor falls back to Advanced Search; narrow the query using author, collection, year or subject to explore other slices. |
| Indexed item has no downloadable format | Many items are borrow-only, private, restricted, missing a supported format or too large. Use the provider's item page to inspect access rules. |
| Download failed or was interrupted | Check the detailed error in **My Library**, try **Retry**, and ensure the destination disk has free space. |
| Already downloaded / duplicate job | BookHarbor reuses an active or completed job for the same item and format. Check **My Library** first. |
| Pytest reports missing Playwright | Use the **`requirements-e2e.txt`** installation steps only if you are running the optional browser tests. |

If a test fails, inspect the GitHub Actions job logs; failing browser jobs can upload screenshots and Playwright traces.

## Catalog status & limitations

| Catalog | What is supported | Known limitation |
|---|---|---|
| **Project Gutenberg** | Public ebook search and direct supported formats, with official OPDS fallback | Availability, mirrors and US public-domain policy vary; do not bulk-harvest their main site. |
| **Internet Archive** | Metadata search, deep local indexing and individually verified public files | Cursor can repeat; Advanced Search fallback limited to 10,000 per query. Borrow-only/restricted items are excluded. |
| **Open Library** | Discovery of records marked as public scans; where available, files resolve through Archive | Coverage depends on source metadata; not all records have downloadable files. |
| **Standard Ebooks** | Search its public **recent-release feed**, with direct offered files | Not a comprehensive full-catalog search. |
| **OAPEN** | Academic metadata via REST where available; limited OAI-PMH fallback | Direct PDF/EPUB files from the fallback are **not verified**; REST may return HTTP 403. |

BookHarbor uses provider APIs where possible, never circumvents DRM or borrowing restrictions, and is intended for controlled personal research. Source licensing and copyright vary by jurisdiction, including Greece.

## Project files

```text
BookHarbor/
├── app.py                        # Local FastAPI web application
├── bookharbor/
│   ├── providers.py              # Provider catalog integrations
│   ├── archive_explorer.py       # Persistent Internet Archive search/index
│   ├── downloads.py              # Safe streamed/resumable downloads
│   └── storage.py                # SQLite download history
├── templates/                     # Browser page templates
├── static/                        # Browser CSS / JavaScript
├── tests/                         # Offline, browser and live integration tests
├── .github/workflows/             # GitHub Actions test automation
├── requirements.txt               # Normal user dependencies
├── requirements-e2e.txt           # Optional Playwright/test dependencies
├── run.sh                         # Linux/macOS startup
├── INSTALLATION.md                 # Historical detailed installation guide
└── LICENSE
```

Further technical details: [Archive Explorer](ARCHIVE_EXPLORER_V03.md) · [Playwright tests](PLAYWRIGHT_E2E.md) · [Provider stability](PROVIDER_STABILITY_V02.md) · [Changelog](CHANGELOG.md).

## License

BookHarbor application code is available under the **MIT License** ([LICENSE](LICENSE)). Downloaded ebook files retain their respective rights, conditions and licenses.
