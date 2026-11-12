"""Real Chromium -> localhost FastAPI -> SQLite end-to-end test.

Only remote Internet Archive responses are stubbed. Search, API actions, job
queue, SQLite, local file writes, and the browser are all real components.
"""
from __future__ import annotations

import hashlib
import importlib
import os
import socket
import threading
import time
from pathlib import Path
from urllib.request import urlopen

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright


PAGE_ITEMS = [
    {"identifier": "bookharbor_e2e_open_a", "title": "Mathematics & Logic",
     "creator": "A. Researcher", "year": "1904", "language": "en", "mediatype": "texts"},
    {"identifier": "bookharbor_e2e_open_b", "title": "An Introduction to Algebra",
     "creator": "B. Scholar", "year": "1912", "language": "en", "mediatype": "texts"},
    {"identifier": "bookharbor_e2e_restricted", "title": "<img src=x onerror=alert(1)> Restricted Edition",
     "creator": "C. Editor", "year": "1920", "language": "en", "mediatype": "texts"},
]


def public_files(identifier: str) -> dict[str, str]:
    if identifier in {"bookharbor_e2e_open_a", "bookharbor_e2e_open_b"}:
        return {"txt": f"https://archive.org/download/{identifier}/sample.txt"}
    return {}


class FakeDownloadResponse:
    """External file response only. The actual downloader writes and hashes it."""
    status_code = 200

    def __init__(self):
        self.data = b"An openly downloadable test book.\n" * 50
        self.headers = {
            "Content-Length": str(len(self.data)),
            "Content-Type": "text/plain",
            "ETag": '"bookharbor-ci-fixed"',
        }

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_content(self, chunk_size=128 * 1024):
        yield self.data


@pytest.fixture
def running_bookharbor(monkeypatch, tmp_path):
    monkeypatch.setenv("BOOKHARBOR_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("BOOKHARBOR_LIBRARY", str(tmp_path / "books"))
    import app as app_module
    app_module = importlib.reload(app_module)
    from bookharbor import archive_explorer, downloads

    app_module.archive_catalog.min_spacing = 0
    monkeypatch.setattr(archive_explorer, "scrape_page", lambda *_: (PAGE_ITEMS, None, len(PAGE_ITEMS)))
    monkeypatch.setattr(app_module, "archive_formats", public_files)
    monkeypatch.setattr(downloads, "safe_get", lambda *_args, **_kwargs: FakeDownloadResponse())

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    host, port = sock.getsockname()
    server = uvicorn.Server(uvicorn.Config(
        app_module.app, host=host, port=port, log_level="error",
        access_log=False, lifespan="off"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    base = f"http://{host}:{port}"
    try:
        for _ in range(100):
            try:
                with urlopen(base + "/api/archive/stats", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("BookHarbor did not start on localhost")
        yield base, app_module, tmp_path
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        app_module.download_executor.shutdown(wait=True)
        sock.close()


def wait_for_saved_jobs(app_module, expected: int, timeout: float = 12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        entries = app_module.store.list(limit=100)
        completed = [item for item in entries if item["status"] == "complete"]
        if len(completed) >= expected:
            return completed
        if any(item["status"] == "failed" for item in entries):
            pytest.fail("BookHarbor download failed: " + repr(entries))
        time.sleep(0.1)
    pytest.fail(f"Expected {expected} complete downloads; jobs={app_module.store.list(limit=100)!r}")


def test_archive_explorer_browser_to_server(running_bookharbor):
    base, app_module, temp = running_bookharbor
    artifact_dir = Path(os.environ.get("PLAYWRIGHT_ARTIFACT_DIR", str(temp / "artifacts")))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    errors = []
    chromium_path = os.environ.get("BOOKHARBOR_CHROMIUM_PATH")
    with sync_playwright() as playwright:
        options = {"headless": True}
        if chromium_path:
            options["executable_path"] = chromium_path
            options["args"] = ["--no-sandbox", "--disable-dev-shm-usage"]
        browser = playwright.chromium.launch(**options)
        context = browser.new_context(
            base_url=base, viewport={"width": 1366, "height": 900},
            accept_downloads=True)
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto("/archive", wait_until="networkidle")
            expect(page.get_by_role("heading", name="Explore the Archive")).to_be_visible()
            expect(page.locator("#archive-workspace")).to_be_hidden()

            # Browser submits a real HTTP request to the actual application.
            page.locator('input[name="query"]').fill("mathematics")
            page.locator("#archive-search-btn").click()
            expect(page.locator("#archive-counter")).to_have_text(
                "3 records indexed in this session", timeout=12000)
            expect(page.locator(".archive-item")).to_have_count(3)
            assert app_module.archive_catalog.stats()["indexed"] == 3
            assert not app_module.store.list(limit=100), "Discovery must not download files"
            assert "session=" in page.url

            # User-supplied catalog HTML is displayed as text, not executed.
            assert page.locator(".archive-item img").count() == 0
            expect(page.locator(".archive-item").nth(2)).to_contain_text("Restricted Edition")

            page.locator("#archive-local-query").fill("Algebra")
            page.locator("#archive-filter-btn").click()
            expect(page.locator(".archive-item")).to_have_count(1)
            page.locator("#archive-local-query").fill("")
            page.locator("#archive-filter-btn").click()
            expect(page.locator(".archive-item")).to_have_count(3)

            # A restricted item does not expose a download control.
            restricted = page.locator(".archive-item").filter(has_text="Restricted Edition")
            restricted.get_by_role("button", name="Inspect open files").click()
            expect(restricted).to_contain_text("Availability: unavailable", timeout=8000)
            assert restricted.locator(".archive-download-file").count() == 0

            # Inspect -> queue -> real SQLite job -> saved file + SHA-256.
            first = page.locator(".archive-item").filter(has_text="Mathematics & Logic")
            first.get_by_role("button", name="Inspect open files").click()
            expect(first.locator(".archive-download-file")).to_have_count(1)
            first.get_by_role("button", name="↓ TXT").click()
            expect(page.locator("#archive-message")).to_contain_text("Queued job #", timeout=8000)
            jobs = wait_for_saved_jobs(app_module, 1)
            assert Path(jobs[0]["path"]).is_file()
            assert hashlib.sha256(Path(jobs[0]["path"]).read_bytes()).hexdigest() == jobs[0]["sha256"]

            # Batch queue uses live app HTTP, not an intercepted API.
            second = page.locator(".archive-item").filter(has_text="Introduction to Algebra")
            second.locator(".archive-choice").check()
            page.locator("#archive-download-btn").click()
            expect(page.locator("#archive-message")).to_contain_text(
                "1 queued, 0 skipped", timeout=8000)
            wait_for_saved_jobs(app_module, 2)
            assert app_module.archive_catalog.stats()["public_verified"] == 2

            # Session survives refresh; library shows completed files.
            page.reload(wait_until="networkidle")
            expect(page.locator(".archive-item")).to_have_count(3)
            page.get_by_role("link", name="My Library").click()
            expect(page).to_have_url(base + "/library")
            expect(page.locator("body")).to_contain_text("Mathematics & Logic")
            expect(page.locator("body")).to_contain_text("Introduction to Algebra")
            expect(page.locator("body")).to_contain_text("complete")
            assert not errors, "Browser JS exceptions: " + repr(errors)
        except Exception:
            page.screenshot(path=str(artifact_dir / "bookharbor-failed.png"), full_page=True)
            context.tracing.stop(path=str(artifact_dir / "bookharbor-failed-trace.zip"))
            raise
        else:
            context.tracing.stop()
        finally:
            context.close()
            browser.close()
