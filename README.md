# BookHarbor v0.2 — Experimental Local Ebook Finder

## Experimental v0.3 — Internet Archive Explorer

A separate feature branch adds [Archive Explorer](ARCHIVE_EXPLORER_V03.md): persistent local metadata indexing via the official cursor-search API, deep pagination, advanced filters, public-file inspection, and resumable downloads with HTTP validator checks. Open `/archive` when running that branch. The stable `main` branch is unchanged until verification and promotion.


**Provider stabilization (feature branch):** Gutenberg OPDS fallback, Archive alternate-node retries, Open Library public-scan filtering, and OAPEN's partial OAI metadata fallback are documented in [PROVIDER_STABILITY_V02.md](PROVIDER_STABILITY_V02.md). The OAPEN fallback is **not** a full searchable or downloadable catalog; see the live CI evidence before relying on a source.


**Experimental branch:** `feature/bookharbor-v0.2-library-upgrade`. See the [v0.2 upgrade guide](UPGRADE_V0_2.md), [changelog](CHANGELOG.md), and [base installation instructions](INSTALLATION.md). The stable `main` branch remains v0.1. This branch has **30 passing offline tests** and verified real downloads from Gutenberg, Internet Archive, and Standard Ebooks. See [live results](LIVE_INTEGRATION_RESULTS.md). OAPEN direct downloads remain unverified.

**v0.2 changes:** Fifth source (**OAPEN academic books**), duplicate-safe queues, SHA-256 checksums with verify buttons, library search/status filters, CSV export, retries for failed/interrupted jobs, and safer filenames.

A **local web application** for finding and downloading openly available ebooks on **Linux Mint, Ubuntu, Debian, Windows or macOS**. It runs on your computer; the web browser is only the interface. Book files and a SQLite download ledger are stored locally.

> **Status:** runnable beta / v0.1, with mocked integration tests. Internet connectivity to upstream catalogs cannot be tested in every environment, and providers can change their APIs or access conditions. Do not treat a search result as a guarantee that a downloadable file or copyright permission exists.

## Included catalogs

| Catalog | Discovery | Download behavior |
|---|---|---|
| **Project Gutenberg** | Gutendex JSON catalog API | Direct EPUB, TXT, PDF or MOBI only when the catalog gives a valid file URL. |
| **Internet Archive** | Advanced Search JSON + individual Metadata API | Downloads only files marked public in metadata, in supported formats. Private/restricted/lending-only items are excluded. Server can still reject the download. |
| **Open Library** | Search API with `ebook_access=public` | Find public-domain/publicly accessible scans, then check their Internet Archive files if a compatible identifier exists. |
| **Standard Ebooks** | Public **new releases** Atom feed only | Shows matching recent books; can download only if the feed contains a direct EPUB/PDF/TXT/MOBI enclosure. The complete OPDS feed requires membership. |
| **OAPEN** | Official REST API, or limited OAI-PMH fallback when REST is blocked | OAI fallback is a **partial recent metadata sample** and may show item links without direct downloadable files. |

OAPEN academic search is integrated in v0.2. **DOAB** (https://www.doabooks.org/) and **OpenStax** (https://openstax.org/) remain prospective future integrations.

This app does **not** bypass DRM, paid access, borrowing time limits, login requirements, anti-bot measures, or source access policies. Search via APIs is preferable to uncontrolled HTML scraping.

## Clone and start directly from GitHub

On Linux Mint / Ubuntu:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
git clone --branch feature/bookharbor-v0.2-library-upgrade https://github.com/SaridakisStamatisChristos/BookHarbor.git
cd BookHarbor
./run.sh
```

Then open **http://127.0.0.1:8765**. The launcher is executable in Git.

For the **stable v0.1 release only**, download the [v0.1 ZIP](releases/BookHarbor_v0_1_Linux_Windows.zip). To run v0.2, use the branch-specific clone command above and follow [UPGRADE_V0_2.md](UPGRADE_V0_2.md).

## Linux Mint / Ubuntu installation

Open **Terminal** in the extracted `BookHarbor_v0_1` folder.

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
chmod +x run.sh
./run.sh
```

The first launch creates `.venv` and installs the Python libraries. Subsequent launches reuse the environment. **Internet access is required to search catalogs and download books.**

Visit: **http://127.0.0.1:8765**

The server is bound to **127.0.0.1** by default, so it does not expose your library to other computers on your network.

Stop with **Ctrl+C**.

### Manual start (Linux / macOS)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

### Windows PowerShell

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

Then open http://127.0.0.1:8765.

## How to use

1. Enter a **title, author or subject**. Select **All sources** or a particular catalog.
2. Optionally use a 2–3-letter language code, e.g. `en` or `el`. Catalog language tagging is imperfect.
3. For Gutenberg and any source that gives direct links, click a file format (EPUB/PDF/TXT/MOBI).
4. For Internet Archive/Open Library results, click **Find files**. Only files the Archive reports as public are offered; borrowing-only books are not made downloadable.
5. To download several books at once, select their checkboxes, set **Preferred format**, and click **Download selected**. Limit: **10 explicitly selected books per action**. It tries the preferred format, falling back to EPUB, PDF, TXT or MOBI.
6. Open **My Library** for queued/completed/failed downloads. Running jobs update on the page about every seven seconds.

## Where are my ebooks?

By default:

- **Books:** `~/.local/share/bookharbor/books/`
- **SQLite download history:** `~/.local/share/bookharbor/jobs.sqlite3`
- **Secret for tamper-proof download buttons:** `~/.local/share/bookharbor/secret.key`

Choose a different location when starting the app:

```bash
export BOOKHARBOR_LIBRARY="$HOME/Books/BookHarbor"
export BOOKHARBOR_HOME="$HOME/.local/share/bookharbor"
export BOOKHARBOR_PORT=8765
export BOOKHARBOR_CONTACT="mailto:your-contact@example.org"
./run.sh
```

`BOOKHARBOR_CONTACT` identifies this installation to library servers in the User-Agent header. Consider using a contact URL or public address as part of good API citizenship. You do not need an API key. **The application does not share its local library database with any cloud service.** It makes outbound requests to the catalog providers you search.

Import the downloaded books into [Calibre](https://calibre-ebook.com/) if you want richer organization, reading metadata, cover retrieval and conversion; BookHarbor itself does not modify book files.

## Safety and service limits

- **Downloads are initiated only by an explicit user click** (individual format or selected batch). No unlimited crawling or mass downloads. Duplicate active/completed editions are reused.
- The app accepts download files from a fixed set of ebook provider domains; redirects outside those domains are rejected. HTTP (unencrypted) and localhost URLs are rejected.
- Internet Archive file metadata is checked before enabling downloads and checked again before single-file queueing. This is a conservative access check, **not a legal rights determination**.
- Download content is streamed to a temporary `.part` file and limited to **350 MiB per file**. Basic PDF/EPUB checks reject obvious HTML error pages.
- A 2-worker queue limits simultaneous downloads. If interrupted, outstanding jobs are marked `interrupted` upon restart rather than silently claimed successful.
- Server is local-only. Do **not** expose it publicly by changing `host=127.0.0.1` without adding authentication, CSRF protection, and more validation.
- Copyright differs by country. **Project Gutenberg's US public-domain status does not automatically establish public-domain status in Greece.** Check the work and the source's license before you download, share or republish it.
- Project Gutenberg requests that automated high-volume downloads use approved mirrors or bulk catalog infrastructure, not its primary website. See https://www.gutenberg.org/policy/robot_access.html.
- Open Library has rate limits and discourages HTML scraping. See https://openlibrary.org/developers/api.

## Troubleshooting

**Port in use:** Start with `BOOKHARBOR_PORT=8766 ./run.sh`, and visit http://127.0.0.1:8766.

**Some catalogs unreachable:** A provider may be down, API throttling may be active, or Internet access may be unavailable. The UI shows source-specific warnings. Try searching a single provider.

**Internet Archive returned no files:** Most commonly the item is borrow-only, has restricted files, has no supported format, or files are above the configured per-file cap. Follow the **Catalog** link to inspect the Archive's own download options.

**Gutenberg download error / permission:** Some catalog download links may be altered or blocked. Avoid large unattended download runs; use Gutenberg's official harvest/mirror guidance for authorized bulk acquisition.

**Standard Ebooks result missing:** The public feed supports recent releases only, not a complete catalog search. Its full catalog OPDS feed may require patron credentials.

**A download failed:** Check **My Library** for the specific error. The original provider may have changed permissions or file URLs.

**No Python 3.10+:** Use Python 3.10 or newer. FastAPI and dependencies also need a supported version of Python; Ubuntu 24.04 and current Linux Mint versions should be suitable.

## Testing

From a terminal (with the virtualenv active), run:

```bash
python -m pip install pytest httpx
python -m pytest -q
```

The **30 offline tests** use controlled simulated responses. A separate networked CI smoke test has successfully downloaded Gutenberg EPUB, Archive TXT, and Standard Ebooks EPUB files. See [verification and limitations](LIVE_INTEGRATION_RESULTS.md).

## Technical structure

```text
BookHarbor_v0_1/
├── app.py                  # Local FastAPI server, signed tokens, UI and endpoints
├── bookharbor/
│   ├── providers.py        # Catalog adapters + conservative Archive file filters
│   ├── downloads.py        # Safe redirect handling, streaming downloads
│   └── storage.py          # SQLite history
├── templates/              # Browser pages
├── static/                 # UI styles + JavaScript
├── tests/                  # Offline automated tests
├── requirements.txt
└── run.sh
```

## Next improvements (not implemented in v0.1)

- Additional academic open-access integrations: DOAB, OpenStax, national libraries. Upgrade OAPEN fallback to a full user-approved local metadata index.
- Metadata and cover caching; duplicate matching across catalogs.
- Full-text indexing of locally owned books.
- Resume partial downloads and per-source bandwidth controls.
- Authorized large-scale import using providers' official data dumps, where their terms permit.
- Calibre export and periodic library integrity checks.

## License

Application code: MIT license (see `LICENSE`). Ebook files remain subject to the terms of their respective sources and rights holders.
