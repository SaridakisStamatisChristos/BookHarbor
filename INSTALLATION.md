# BookHarbor — Installation and Setup Guide

**Version:** BookHarbor v0.1  
**Platforms:** Linux Mint / Ubuntu / Debian, Windows 10/11, macOS  
**Repository:** https://github.com/SaridakisStamatisChristos/BookHarbor  
**Application address:** http://127.0.0.1:8765

BookHarbor is a **locally hosted web app**. It runs on your own computer; you control it in your normal browser. It searches supported ebook catalogs over the internet, and stores downloaded files and its download history locally.

> **Release status:** Beta. The bundled tests use simulated catalog responses. Individual upstream services and live downloads can change or fail. An ebook appearing in search results does not necessarily mean that a downloadable format is available or legally usable in your country.

## 1. Requirements

- Python **3.10 or newer**.
- Internet access for installing Python packages, searching ebook sources, and downloading books.
- A web browser, such as Firefox, Chrome, or Edge.
- Free disk space for ebooks. Individual downloads are currently limited to 350 MiB.
- **Git** if installing from a clone. Git is not needed for ZIP installation.
- **No API keys** and no cloud-hosting account are required.

The application installs Python dependencies listed in `requirements.txt`: FastAPI, Uvicorn, Jinja2, Requests and ItsDangerous.

## 2. Linux Mint / Ubuntu: recommended installation

### 2.1 Install system prerequisites

Open **Terminal** and enter:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
```

Verify Python:

```bash
python3 --version
```

The version must be 3.10 or newer.

### 2.2 Clone BookHarbor from GitHub

```bash
git clone https://github.com/SaridakisStamatisChristos/BookHarbor.git
cd BookHarbor
```

### 2.3 Start the application

```bash
./run.sh
```

The launcher automatically:

1. Changes to the application directory.
2. Creates an isolated `.venv/` Python environment if missing.
3. Installs packages from `requirements.txt`.
4. Runs `app.py`.

Keep this terminal open while using BookHarbor. In your browser visit:

**http://127.0.0.1:8765**

To stop the app, return to the terminal and press **Ctrl+C**.

### 2.4 Start it again later

```bash
cd ~/BookHarbor
./run.sh
```

The `~/BookHarbor` path assumes you originally cloned it from your home directory. Use its actual path if you installed it elsewhere.

> If you get `Permission denied` from the script, run `chmod +x run.sh`, or start it with `bash run.sh`.

## 3. Alternative: install from a ZIP without Git

1. Download the [BookHarbor v0.1 ZIP](releases/BookHarbor_v0_1_Linux_Windows.zip), or use **Code → Download ZIP** on the [repository](https://github.com/SaridakisStamatisChristos/BookHarbor).
2. Extract it into a folder you can access.
3. Open a terminal or PowerShell **inside the folder that contains `app.py`, `requirements.txt` and `run.sh`**. The release ZIP may contain a top-level `BookHarbor_v0_1` directory.
4. Follow the instructions for your operating system below. On Linux, the last command is `bash run.sh`.

If you use the release ZIP, you will not have Git metadata for `git pull`. To update, download and extract a newer release while retaining your separately stored book library.

## 4. Windows 10 / 11 installation

### 4.1 Prepare Python and (optionally) Git

Install Python **3.10+** from https://www.python.org/downloads/windows/ and enable the option to add Python to PATH if offered. For Git-based installation, install Git from https://git-scm.com/downloads/win.

Open a **new PowerShell** window and check:

```powershell
py --version
```

If cloning, run:

```powershell
git clone https://github.com/SaridakisStamatisChristos/BookHarbor.git
cd BookHarbor
```

Alternatively, download and extract the ZIP and use PowerShell to enter the extracted application directory.

### 4.2 Create the environment and run

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Open **http://127.0.0.1:8765** in your browser. Press **Ctrl+C** in PowerShell to stop.

For subsequent launches, from the BookHarbor directory:

```powershell
.\.venv\Scripts\python.exe app.py
```

The Linux `run.sh` script is not intended for standard Windows PowerShell.

## 5. macOS installation

You need Python 3.10+ and Git. Install them using your preferred package manager or their official installers. If you use Homebrew, you can run `brew install python git` as needed.

Open **Terminal**:

```bash
git clone https://github.com/SaridakisStamatisChristos/BookHarbor.git
cd BookHarbor
bash run.sh
```

Then visit **http://127.0.0.1:8765**. Stop with **Ctrl+C**.

If you prefer not to use the launcher:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

## 6. First-use walkthrough

1. Start BookHarbor and open **http://127.0.0.1:8765**.
2. Search by title, author or subject; optionally select a source or language (e.g. `en` or `el`).
3. Available sources in v0.1 include **Project Gutenberg, Internet Archive, Open Library**, and the **public recent-releases feed from Standard Ebooks**.
4. Download a directly offered EPUB, PDF, TXT or MOBI file, or use **Find files** for Internet Archive / Open Library items.
5. Use **Download selected** for up to **10 individually selected titles per operation**.
6. Open **My Library** to inspect downloads and their status.

Borrow-only, restricted and DRM-protected files are not bypassed. Academic catalogs such as DOAB and OAPEN are **not integrated** in v0.1.

## 7. Where downloads and application data live

Defaults:

| Data | Linux / macOS (default) |
|---|---|
| Downloaded ebooks | `~/.local/share/bookharbor/books/` |
| Download history | `~/.local/share/bookharbor/jobs.sqlite3` |
| Local signing secret | `~/.local/share/bookharbor/secret.key` |

On Windows, these same `~/.local/share/bookharbor` defaults resolve relative to your Windows user home directory. You can change them using environment variables.

### Optional: customize the ebook directory on Linux

```bash
mkdir -p "$HOME/Books/BookHarbor"
export BOOKHARBOR_LIBRARY="$HOME/Books/BookHarbor"
./run.sh
```

To keep this choice across launches, create a small personal launcher script outside the repository, or export the variable before each launch.

Other settings:

| Environment variable | Purpose | Default |
|---|---|---|
| `BOOKHARBOR_LIBRARY` | Directory where ebook files are stored | `<BOOKHARBOR_HOME>/books` |
| `BOOKHARBOR_HOME` | Application state directory | `~/.local/share/bookharbor` |
| `BOOKHARBOR_PORT` | Browser server port | `8765` |
| `BOOKHARBOR_CONTACT` | Optional contact identifier for provider requests | Unset |

For example, to use port 8766 on Linux:

```bash
BOOKHARBOR_PORT=8766 ./run.sh
```

On Windows PowerShell:

```powershell
$env:BOOKHARBOR_PORT = "8766"
.\.venv\Scripts\python.exe app.py
```

Use **http://127.0.0.1:8766** in that case.

## 8. Update an existing Git installation

From the BookHarbor source directory:

```bash
git pull --ff-only
./run.sh
```

The launcher rechecks the required Python packages. If you have local code changes, `git pull --ff-only` may refuse to continue; preserve or commit your changes before updating.

Downloads and the database are stored outside the repository by default, so code updates should not replace your book library. Back up your data before major upgrades.

For Windows, run `git pull --ff-only` and then rerun the Windows Python command in section 4.

## 9. Run automated tests (optional)

On Linux or macOS, after the initial launcher has created the environment:

```bash
.venv/bin/python -m pip install pytest httpx
.venv/bin/python -m pytest -q
```

On Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install pytest httpx
.\.venv\Scripts\python.exe -m pytest -q
```

These are **mocked/offline tests**, not guarantees that upstream APIs are currently functioning.

## 10. Troubleshooting

**`python3: command not found` or Python is too old:** Install Python 3.10+ and verify its version before starting.

**`No module named venv` (Ubuntu/Mint):** Run `sudo apt install python3-venv` and retry.

**`Permission denied: ./run.sh`:** Run `chmod +x run.sh` or `bash run.sh`.

**`No module named fastapi` or similar:** Ensure you are using the virtual environment. On Linux run `.venv/bin/python -m pip install -r requirements.txt`; on Windows run `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.

**Browser says the site cannot be reached:** Ensure the BookHarbor terminal is still running and use **http://127.0.0.1:8765** rather than a public website URL. Try another port if it is already occupied.

**The desired book appears but cannot be downloaded:** The title might be borrow-only, restricted, unavailable in the chosen format, or blocked by a provider. BookHarbor does not circumvent those limits.

**Downloads fail after searching:** Check **My Library** for the failure status. Providers may rate-limit requests, change file URLs or reject a request.

**Missing book files:** Check the library directory in section 7 and ensure it is writable and has sufficient free space.

**Security:** The server listens only on `127.0.0.1` by default. Do not configure it for remote/public access without first adding authentication and other security protections.

## 11. Legal and service-use notes

Download only files that the source makes available to you and that you are allowed to use. Copyright and public-domain rules differ between countries: Project Gutenberg's US eligibility is not automatically the same as eligibility in Greece. Respect library API rate limits and service policies. BookHarbor v0.1 is intentionally **not** an unlimited scraper or DRM bypass tool.

For general information see the [main README](README.md).
