"""Shared fixtures for the backend tests.

Nothing here may touch the real world: the database, the cookies file, the
download folder and the SMB credentials directory all live in temp
directories, and yt-dlp is replaced by a small fake script. As a second line
of defence a directory of "guard" stubs is put first on PATH, so a test that
would start the real yt-dlp, ffmpeg, mount or umount fails the whole run.
"""

import atexit
import json
import os
import shutil
import stat
import sys
import tempfile
import textwrap

# models/database.py reads DATABASE_PATH and creates the engine at import
# time, so this must happen before any backend module is imported.
_SESSION_DIR = tempfile.mkdtemp(prefix="ytdlp-ui-tests-")
atexit.register(shutil.rmtree, _SESSION_DIR, ignore_errors=True)
_DATA_DIR = os.path.join(_SESSION_DIR, "data")
os.makedirs(_DATA_DIR)
os.environ["DATABASE_PATH"] = os.path.join(_DATA_DIR, "test.db")

_GUARD_DIR = os.path.join(_SESSION_DIR, "guard-bin")
_GUARD_LOG = os.path.join(_SESSION_DIR, "guard-calls.log")
os.makedirs(_GUARD_DIR)
for _name in ("yt-dlp", "ffmpeg", "mount", "umount", "mount.cifs", "mount.nfs"):
    _path = os.path.join(_GUARD_DIR, _name)
    with open(_path, "w") as _fh:
        _fh.write(
            "#!/bin/sh\n"
            f'echo "{_name} $*" >> "{_GUARD_LOG}"\n'
            f'echo "tests must not run the real {_name}" >&2\n'
            "exit 97\n"
        )
    os.chmod(_path, 0o755)
os.environ["PATH"] = _GUARD_DIR + os.pathsep + os.environ.get("PATH", "")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api.routes import settings as settings_routes  # noqa: E402
from main import app  # noqa: E402
from models import database  # noqa: E402
from services import cookies, share_manager  # noqa: E402
from services.download_manager import manager  # noqa: E402

FAKE_YTDLP_VERSION = "2099.01.01-fake"
FAKE_TITLE = "Fake Title"

# What the fake does:
#   --version            print FAKE_YTDLP_VERSION
#   --dump-single-json   print a small JSON document with "title"
#   anything else        a "download": print progress lines, create
#                        <output dir>/Fake Title.mp4 (.mp3 with -x) and print
#                        "OUTPATH <path>"
# A URL containing "fail" makes it exit 1 with an ERROR line instead.
# Every call appends its arguments (one JSON list per line) to
# <script>.calls so tests can check what the app really ran.
_FAKE_YTDLP_SOURCE = textwrap.dedent(
    '''\
    #!{python}
    import json, os, sys

    args = sys.argv[1:]
    with open(__file__ + ".calls", "a") as fh:
        fh.write(json.dumps(args) + "\\n")

    if "--version" in args:
        print("{version}")
        sys.exit(0)

    url = args[-1] if args else ""
    if "fail" in url:
        print("ERROR: [fake] " + url + ": simulated failure")
        sys.exit(1)

    if "--dump-single-json" in args:
        print(json.dumps({{
            "title": "{title}",
            "thumbnail": "http://media.invalid/thumb.jpg",
            "uploader": "Fake Uploader",
            "duration": 42,
            "formats": [
                {{"format_id": "18", "ext": "mp4", "height": 360,
                  "vcodec": "avc1", "acodec": "mp4a", "filesize": 1000}},
                {{"format_id": "140", "ext": "m4a", "vcodec": "none",
                  "acodec": "mp4a", "filesize": 100}},
            ],
        }}))
        sys.exit(0)

    template = args[args.index("-o") + 1]
    ext = "mp3" if "-x" in args else "mp4"
    out = os.path.join(os.path.dirname(template), "{title}." + ext)
    print("PROGRESS downloading  50.0% 1.00MiB/s 00:01", flush=True)
    with open(out, "w") as fh:
        fh.write("fake media\\n")
    print("PROGRESS finished 100.0% NA NA", flush=True)
    print("OUTPATH " + out, flush=True)
    '''
)


def pytest_sessionfinish(session, exitstatus):
    """Fail the run if any test reached a real external program."""
    if os.path.exists(_GUARD_LOG):
        with open(_GUARD_LOG) as fh:
            calls = fh.read().strip()
        session.exitstatus = 1
        sys.stderr.write(
            "\nERROR: tests started real external programs:\n" + calls + "\n"
        )


def _reset_state() -> None:
    """Fresh database file, no cookies file, empty in-memory singletons."""
    for name in os.listdir(_DATA_DIR):
        os.remove(os.path.join(_DATA_DIR, name))
    settings_routes._version_cache.clear()
    # The manager is a process-wide singleton whose queue binds to the event
    # loop of the first app start; every TestClient has its own loop.
    manager.__init__()


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Applies to every test, including the ones that do not use `client`."""
    assert database.DATA_DIR == _DATA_DIR
    assert cookies.COOKIES_PATH == os.path.join(_DATA_DIR, "cookies.txt")
    _reset_state()
    monkeypatch.setattr(share_manager, "_CREDS_DIR", str(tmp_path / "share-creds"))
    yield


@pytest.fixture
def fake_ytdlp(tmp_path) -> str:
    """Path of an executable fake yt-dlp (see _FAKE_YTDLP_SOURCE)."""
    path = tmp_path / "fake-bin" / "yt-dlp"
    path.parent.mkdir()
    path.write_text(
        _FAKE_YTDLP_SOURCE.format(
            python=sys.executable, version=FAKE_YTDLP_VERSION, title=FAKE_TITLE
        )
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


@pytest.fixture
def fake_ytdlp_calls(fake_ytdlp):
    """Callable returning the argument lists the fake was started with."""

    def calls() -> list[list[str]]:
        try:
            with open(fake_ytdlp + ".calls") as fh:
                return [json.loads(line) for line in fh if line.strip()]
        except FileNotFoundError:
            return []

    return calls


@pytest.fixture
def download_root(tmp_path) -> str:
    """The temp directory the `client` fixture sets as download folder."""
    root = tmp_path / "downloads"
    root.mkdir()
    return str(root)


@pytest.fixture
def client(fake_ytdlp, download_root):
    """TestClient with the app's lifespan running and fresh tables.

    The download folder points at `download_root` and yt-dlp at the fake, so
    no request can reach /downloads or a real yt-dlp.
    """
    with TestClient(app) as test_client:
        resp = test_client.post(
            "/api/settings",
            json={"ytdlp_path": fake_ytdlp, "download_folder": download_root},
        )
        assert resp.status_code == 200, resp.text
        try:
            yield test_client
        finally:
            # Close pooled connections on the loop that opened them, so the
            # next test starts with a new database file.
            test_client.portal.call(database.engine.dispose)
