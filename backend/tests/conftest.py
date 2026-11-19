"""Shared fixtures for the backend tests.

Rules these fixtures enforce for every test:

* The database, download folder, cookies file and SMB credentials directory
  all live under pytest's ``tmp_path``. Nothing is written outside it.
* No real program is ever started. ``asyncio.create_subprocess_exec`` is
  replaced by :class:`FakeSubprocess`, which records the argument list and
  plays back canned output for ``yt-dlp``, ``mount`` and ``umount``.
* No network. Outgoing ``connect`` calls on IP sockets raise.

The backend reads ``DATABASE_PATH`` and builds its engine and the download
manager singleton at import time, so each test gets a freshly imported copy of
the application modules.
"""

import asyncio
import json
import socket
import sqlite3
import sys
import time
from types import SimpleNamespace

import pytest

APP_PACKAGES = ("main", "api", "models", "services")


def _purge_app_modules() -> None:
    for name in list(sys.modules):
        if name in APP_PACKAGES or name.startswith(tuple(p + "." for p in APP_PACKAGES)):
            del sys.modules[name]


class FakeStream:
    def __init__(self, lines):
        self._lines = [
            (line if isinstance(line, bytes) else line.encode()) + b"\n" for line in lines
        ]

    async def readline(self) -> bytes:
        # Yield to the loop like a real pipe would.
        await asyncio.sleep(0)
        return self._lines.pop(0) if self._lines else b""


class FakeProcess:
    def __init__(self, returncode: int = 0, output: bytes = b"", lines=()):
        self.returncode = None
        self._returncode = returncode
        self._output = output
        self.stdout = FakeStream(lines)
        self.terminated = False

    async def communicate(self):
        self.returncode = self._returncode
        return self._output, b""

    async def wait(self) -> int:
        self.returncode = self._returncode
        return self._returncode

    def terminate(self) -> None:
        self.terminated = True


class FakeSubprocess:
    """Stand-in for ``asyncio.create_subprocess_exec``.

    ``calls`` holds every argument list the application tried to run.
    """

    version = "2099.01.01"

    def __init__(self):
        self.calls: list[list[str]] = []
        self.metadata = {"title": "Fake Title", "thumbnail": "https://img.invalid/t.jpg"}
        self.download_lines: list[str] = []
        self.download_returncode = 0
        self.mount_returncode = 0
        self.mount_output = b""

    async def __call__(self, *args, **_kwargs):
        argv = [str(a) for a in args]
        self.calls.append(argv)
        if argv[0] in ("mount", "umount"):
            return FakeProcess(self.mount_returncode, self.mount_output)
        if "--version" in argv:
            return FakeProcess(0, self.version.encode() + b"\n")
        if "--dump-single-json" in argv:
            return FakeProcess(0, json.dumps(self.metadata).encode())
        return FakeProcess(self.download_returncode, lines=self.download_lines)

    def calls_to(self, program: str) -> list[list[str]]:
        return [c for c in self.calls if c[0] == program]

    def download_calls(self) -> list[list[str]]:
        return [
            c
            for c in self.calls
            if c[0] not in ("mount", "umount")
            and "--version" not in c
            and "--dump-single-json" not in c
        ]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    real_connect = socket.socket.connect

    def guarded_connect(self, address, *args, **kwargs):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError(f"test tried to open a network connection to {address!r}")
        return real_connect(self, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


@pytest.fixture
def backend(tmp_path, monkeypatch):
    """Freshly imported application modules bound to a temp database.

    The app is imported but not started; use ``client`` for HTTP tests.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))

    fake = FakeSubprocess()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake)

    _purge_app_modules()
    import main
    from models import database, schemas
    from services import cookies, download_manager, files_manager, share_manager

    creds_dir = tmp_path / "share-creds"
    monkeypatch.setattr(share_manager, "_CREDS_DIR", str(creds_dir))

    yield SimpleNamespace(
        app=main.app,
        database=database,
        schemas=schemas,
        cookies=cookies,
        download_manager=download_manager,
        files_manager=files_manager,
        share_manager=share_manager,
        subprocess=fake,
        tmp_path=tmp_path,
        data_dir=data_dir,
        db_path=db_path,
        creds_dir=creds_dir,
    )
    _purge_app_modules()


@pytest.fixture
def client(backend):
    """HTTP client with the app started (lifespan run, download workers up)."""
    from fastapi.testclient import TestClient

    with TestClient(backend.app) as test_client:
        yield test_client
        # Close pooled connections on the loop that opened them.
        test_client.portal.call(backend.database.engine.dispose)


@pytest.fixture
def downloads_dir(backend, client):
    """A temp download folder, configured through the settings API."""
    folder = backend.tmp_path / "downloads"
    folder.mkdir()
    response = client.post("/api/settings", json={"download_folder": str(folder)})
    assert response.status_code == 200, response.text
    return folder


@pytest.fixture
def db(backend):
    """Run a statement against the temp database (after the app created it)."""

    def execute(sql: str, params=()):
        with sqlite3.connect(backend.db_path) as conn:
            return conn.execute(sql, params).fetchall()

    return execute


@pytest.fixture
def wait_for_job(client):
    def wait(job_id: str, statuses=("finished", "failed", "cancelled"), timeout: float = 5.0):
        deadline = time.monotonic() + timeout
        job = None
        while time.monotonic() < deadline:
            jobs = {j["id"]: j for j in client.get("/api/jobs").json()}
            job = jobs.get(job_id)
            if job and job["status"] in statuses:
                return job
            time.sleep(0.02)
        raise AssertionError(f"job {job_id} did not reach {statuses}; last seen: {job}")

    return wait
