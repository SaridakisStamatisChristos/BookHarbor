# BookHarbor v0.2 — Upgrade Guide (experimental branch)

**Branch:** `feature/bookharbor-v0.2-library-upgrade`  
**Base:** `main` (v0.1), which remains unchanged until a separately authorized merge.

BookHarbor v0.2 improves the local ebook research workflow. It adds an **OAPEN academic open-access search adapter**, prevents repeatedly queuing an already downloaded/active edition, and improves local library management.

## What's new

- **Five catalog adapters:** Project Gutenberg, Internet Archive, Open Library, Standard Ebooks' public recent releases, and **OAPEN** academic open-access books. The OAPEN adapter uses its documented repository REST API and only offers direct files hosted on OAPEN. Catalog entries without a safe link remain discovery-only. Live upstream behavior requires real-world testing.
- **Duplicate-safe queues:** If the same catalog item and file format is already queued, downloading, or successfully stored, another click reuses its existing job rather than creating a second copy. If a previously recorded file has gone missing, a new download is permitted.
- **SHA-256 integrity:** New downloads record a cryptographic checksum in the SQLite history. Use **Verify file** in the library to compare the saved file against its recorded checksum. Legacy v0.1 files appear as *untracked* and remain accessible.
- **Library search and status filters:** Find downloads by title, author, or source; filter by completed, queued, running, failed, or interrupted.
- **CSV export:** Download a local spreadsheet-friendly history export (with dangerous spreadsheet formula prefixes escaped). This exports book metadata, not the ebook contents.
- **Retry buttons:** Failed and interrupted jobs can be retried; Internet Archive and Open Library items are rechecked against public-file metadata before being queued. Retry creates a new job record, keeping the previous failure in the audit history.
- **Collision-safe filenames:** New files include the job ID so separate editions with the same author/title do not overwrite each other.
- **Compatibility:** Existing v0.1 SQLite data receives an automatic additive column migration; existing books and original history records are preserved.

## Install the experimental branch on Linux Mint / Ubuntu

To try it in a **new source directory** without replacing your main-branch checkout:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip

git clone --branch feature/bookharbor-v0.2-library-upgrade \
  https://github.com/SaridakisStamatisChristos/BookHarbor.git BookHarbor-v0.2
cd BookHarbor-v0.2
./run.sh
```

Open **http://127.0.0.1:8765**.

The default library and database directory are shared across version checkouts (`~/.local/share/bookharbor/`). To test without modifying your existing v0.1 history, use **isolated data paths**:

```bash
export BOOKHARBOR_HOME="$HOME/.local/share/bookharbor-v0.2-test"
export BOOKHARBOR_LIBRARY="$HOME/Books/BookHarbor-v0.2-test"
./run.sh
```

Set those variables **before** running the launcher, and use the same values for all runs of the test installation. Avoid launching v0.1 and v0.2 simultaneously against the same database.

To upgrade your existing checkout instead, first commit/stash any local changes, back up the database and books, then:

```bash
cd ~/BookHarbor
cp -a "$HOME/.local/share/bookharbor" "$HOME/.local/share/bookharbor-backup"
git fetch origin
git switch --track origin/feature/bookharbor-v0.2-library-upgrade
./run.sh
```

The above backup assumes the default data location. If you configured custom paths, back up those directories instead. Never remove your download folder to switch branches.

For Windows and macOS, refer to [INSTALLATION.md](INSTALLATION.md). Replace the clone command there with:

```bash
git clone --branch feature/bookharbor-v0.2-library-upgrade https://github.com/SaridakisStamatisChristos/BookHarbor.git
```

## Verify with offline tests

In the project root (Linux / macOS):

```bash
.venv/bin/python -m pip install pytest httpx
.venv/bin/python -m pytest -q
```

**Development validation at this checkpoint: 21 offline tests pass.** These use simulated responses for external catalogs; they do not assert that any upstream API or downloadable file is currently reachable.

## Known limits

- This is an **experimental branch**, not the stable `main` release.
- OAPEN file availability depends on its REST metadata and the repository's present download policies. Other publisher-hosted files are not automatically followed or downloaded.
- BookHarbor does not bypass lending, authentication, DRM, or copyright rules. License conditions vary by work and country.
- Search results are limited previews, not exhaustive bulk harvesting. Batch actions require selecting up to 10 titles explicitly.
- The library screen shows the latest 200 matching jobs; CSV export is capped for resource safety.
- An integrity check covers recorded file bytes, not whether the source has changed since download.

**Reference:** [OAPEN's official REST search documentation](https://www.oapen.org/article/8185269-search-using-a-rest-api).
