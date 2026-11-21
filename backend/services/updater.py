"""Self-update: version check against GitHub and the update job.

Nothing here takes a ref, path or command from a request. The target is
always a 40-character commit SHA that this module reads from GitHub itself,
and every program is started with a fixed argument list (never a shell).
"""

import asyncio
import hmac
import json
import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

REPO = os.environ.get("UPDATE_REPO", "thelorax1775/yt-dlp-ui")
API = "https://api.github.com"
_SHA = re.compile(r"^[0-9a-f]{40}$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
MODES = ("docker", "systemd")
SYSTEMD_UNITS = ("ytdlp-backend", "ytdlp-frontend")
DOCKER_CLI_IMAGE = "docker:27-cli"
STEP_TIMEOUT = 1800
MAX_LOG_LINES = 400
CHECK_CACHE_SECONDS = 600

# Tests replace this to avoid the network.
_transport: httpx.AsyncBaseTransport | None = None

# Lock to prevent concurrent start_update calls during the "starting" phase
_start_update_lock = asyncio.Lock()

# Cache for latest_version()
_cache_latest_version: dict | None = None
_cache_latest_version_time: float = 0.0


def _cache_clear() -> None:
    """Clear the latest_version cache. For tests."""
    global _cache_latest_version, _cache_latest_version_time
    _cache_latest_version = None
    _cache_latest_version_time = 0.0


def _is_rate_limit_response(r: httpx.Response) -> bool:
    """Check if response indicates GitHub rate limit exceeded."""
    if r.status_code == 429:
        return True
    if r.status_code == 403:
        remaining = r.headers.get("x-ratelimit-remaining")
        if remaining is not None and remaining == "0":
            return True
    return False


def mode() -> str | None:
    value = os.environ.get("UPDATE_MODE", "").strip().lower()
    return value if value in MODES else None


def app_dir() -> Path:
    raw = os.environ.get("UPDATE_APP_DIR")
    return Path(raw) if raw else Path(__file__).resolve().parents[2]


def admin_token() -> str | None:
    return os.environ.get("UPDATE_ADMIN_TOKEN") or None


def check_admin(supplied: str | None) -> bool:
    """True only when an admin token is configured and ``supplied`` matches."""
    expected = admin_token()
    if not expected or not supplied:
        return False
    return hmac.compare_digest(expected.encode(), supplied.encode())


def installed_version() -> str:
    """Commit SHA baked in at build time (APP_VERSION), else the checkout's HEAD."""
    baked = (os.environ.get("APP_VERSION") or "").strip()
    if baked and baked != "unknown":
        return baked
    try:
        git = app_dir() / ".git"
        head = (git / "HEAD").read_text().strip()
        if head.startswith("ref: "):
            ref = head[5:]
            if ".." in ref:
                return "unknown"
            # Try loose ref first
            loose_ref = git / ref
            if loose_ref.exists():
                head = loose_ref.read_text().strip()
            else:
                # Fall back to packed-refs
                head = _read_packed_ref(git, ref)
        return head if _SHA.match(head) else "unknown"
    except OSError:
        return "unknown"


def _read_packed_ref(git: Path, ref: str) -> str:
    """Read a ref from .git/packed-refs. Returns empty string if not found."""
    packed = git / "packed-refs"
    if not packed.exists():
        return ""
    try:
        for line in packed.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("^"):
                continue
            # Format: <sha> <refname>
            parts = line.split(" ", 1)
            if len(parts) == 2 and parts[1] == ref:
                return parts[0]
    except OSError:
        pass
    return ""


def compare_versions(installed: str, latest: str) -> str:
    """'older', 'equal', 'newer' or 'unknown' (installed relative to latest).

    Understands release tags (1.2.3 / v1.2.3) and commit SHAs. Two different
    SHAs cannot be ordered without the repository history: 'unknown'.
    """
    a, b = _SEMVER.match(installed.strip()), _SEMVER.match(latest.strip())
    if a and b:
        x, y = tuple(map(int, a.groups())), tuple(map(int, b.groups()))
        return "equal" if x == y else ("older" if x < y else "newer")
    i, l_ = installed.strip().lower(), latest.strip().lower()
    if i and l_ and i != "unknown" and (i.startswith(l_) or l_.startswith(i)):
        return "equal"
    return "unknown"


async def _get(path: str):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "yt-dlp-ui-updater"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(transport=_transport, timeout=15, headers=headers) as c:
        return await c.get(f"{API}{path}")


async def latest_version() -> dict:
    """Newest release (tag + commit) or, with no releases, the default branch head."""
    global _cache_latest_version, _cache_latest_version_time
    if not _REPO_RE.match(REPO):
        raise ValueError("UPDATE_REPO is not owner/name")
    
    # Check cache
    now = time.monotonic()
    if _cache_latest_version is not None and (now - _cache_latest_version_time) < CHECK_CACHE_SECONDS:
        return _cache_latest_version
    
    return await _latest_version_fresh()


async def _latest_version_fresh() -> dict:
    """Latest version without using cache. Used by start_update()."""
    global _cache_latest_version, _cache_latest_version_time
    if not _REPO_RE.match(REPO):
        raise ValueError("UPDATE_REPO is not owner/name")
    
    r = await _get(f"/repos/{REPO}/releases/latest")
    # Check for rate limit on any response
    if _is_rate_limit_response(r):
        raise LookupError("rate_limit")
    if r.status_code == 200:
        tag = str(r.json().get("tag_name") or "")
        c = await _get(f"/repos/{REPO}/commits/{quote(tag, safe='')}")
        if _is_rate_limit_response(c):
            raise LookupError("rate_limit")
        if c.status_code == 200 and _SHA.match(str(c.json().get("sha", ""))):
            result = {"kind": "release", "label": tag, "sha": c.json()["sha"]}
            # Cache successful result
            _cache_latest_version = result
            _cache_latest_version_time = time.monotonic()
            return result
        raise LookupError(f"could not resolve release {tag!r}")
    if r.status_code in (401, 403, 404):
        if r.status_code != 404:
            raise PermissionError(r.status_code)
        c = await _get(f"/repos/{REPO}/commits/HEAD")
        if _is_rate_limit_response(c):
            raise LookupError("rate_limit")
        if c.status_code == 200 and _SHA.match(str(c.json().get("sha", ""))):
            sha = c.json()["sha"]
            result = {"kind": "branch", "label": sha[:7], "sha": sha}
            # Cache successful result
            _cache_latest_version = result
            _cache_latest_version_time = time.monotonic()
            return result
        if c.status_code in (401, 403, 404):
            raise PermissionError(c.status_code)
    raise LookupError(f"GitHub answered {r.status_code}")


async def _relation(installed: str, latest_sha: str) -> str:
    """Installed commit relative to the newest one, using local rules then GitHub."""
    quick = compare_versions(installed, latest_sha)
    if quick != "unknown":
        return quick
    if not _SHA.match(installed):
        return "unknown"
    r = await _get(f"/repos/{REPO}/compare/{installed}...{latest_sha}")
    if r.status_code != 200:
        return "unknown"
    return {"identical": "equal", "ahead": "older", "behind": "newer", "diverged": "diverged"}.get(
        r.json().get("status"), "unknown"
    )


async def check() -> dict:
    installed = installed_version()
    out = {
        "installed": installed,
        "latest": None,
        "state": "error",
        "message": "",
        "mode": mode(),
        "token_configured": bool(os.environ.get("GITHUB_TOKEN")),
        "update_enabled": bool(mode() and admin_token()),
        "update_available": False,
    }
    try:
        latest = await latest_version()
    except PermissionError:
        out["state"] = "unreachable"
        out["message"] = (
            "Cannot reach GitHub: access refused. Set GITHUB_TOKEN on the backend "
            "if the repository is private."
            if not out["token_configured"]
            else "Cannot reach GitHub: the configured GITHUB_TOKEN was refused."
        )
        return out
    except LookupError as e:
        if str(e) == "rate_limit":
            out["state"] = "unreachable"
            out["message"] = (
                "GitHub's request limit is used up; try again later or set GITHUB_TOKEN on the backend."
            )
            return out
        out["state"] = "unreachable"
        out["message"] = f"Cannot reach GitHub ({type(e).__name__})."
        return out
    except (httpx.HTTPError, ValueError) as e:
        out["state"] = "unreachable"
        out["message"] = f"Cannot reach GitHub ({type(e).__name__})."
        return out
    out["latest"] = latest
    rel = await _relation(installed, latest["sha"])
    if rel == "equal":
        out["state"], out["message"] = "up_to_date", "Up to date."
    elif rel == "newer":
        out["state"], out["message"] = "ahead", "Installed version is newer than GitHub's."
    elif rel in ("older", "diverged"):
        out["state"], out["update_available"] = "update_available", True
        out["message"] = "A newer version is available."
    else:
        out["state"] = "unknown"
        out["message"] = "Installed version is unknown; cannot compare."
        out["update_available"] = installed == "unknown"
    return out


# ---- the update job ----


class StepFailed(Exception):
    pass


_job: dict | None = None
_task: asyncio.Task | None = None


def _state_file() -> Path:
    return Path(os.environ.get("DATABASE_PATH", "./ytdlp_ui.db")).resolve().parent / "update_job.json"


def _save() -> None:
    try:
        _state_file().write_text(json.dumps(_job))
    except OSError:
        logger.warning("could not save update job state")


def _log(line: str) -> None:
    assert _job is not None
    _job["log"].append(line)
    del _job["log"][:-MAX_LOG_LINES]
    _save()


def get_job() -> dict | None:
    global _job
    if _job is None:
        try:
            _job = json.loads(_state_file().read_text())
        except (OSError, ValueError):
            return None
    return _job


def resolve_after_restart() -> None:
    """On startup: a job left 'restarting' succeeded iff we now run its target."""
    job = get_job()
    if job and job.get("status") in ("running", "restarting"):
        if job.get("status") == "restarting" and installed_version() == job.get("target"):
            job["status"] = "succeeded"
            job["log"].append("Restarted on the new version.")
        else:
            job["status"] = "failed"
            job["error"] = "Interrupted: the backend restarted before the update finished."
        _save()


async def _run(argv: list[str], cwd: Path, extra_env: dict | None = None) -> str:
    if argv[0] == "git":
        argv = ["git", "-c", f"safe.directory={cwd}", *argv[1:]]
    _log("$ " + " ".join(argv))
    env = {**os.environ, **(extra_env or {})}
    env.pop("GITHUB_TOKEN", None)
    env.pop("UPDATE_ADMIN_TOKEN", None)
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=STEP_TIMEOUT)
    except (OSError, asyncio.TimeoutError) as e:
        raise StepFailed(f"{argv[0]} could not run: {type(e).__name__}") from e
    text = out.decode(errors="replace") if isinstance(out, bytes) else ""
    for line in text.strip().splitlines()[-20:]:
        _log("  " + line)
    if proc.returncode != 0:
        raise StepFailed(f"{' '.join(argv[:3])} failed (exit {proc.returncode})")
    return text.strip()


def _build_steps(m: str, d: Path, sha: str) -> list[tuple[list[str], dict]]:
    """Steps that prepare the new version without touching the running one."""
    if m == "docker":
        compose = ["docker", "compose", "-f", str(d / "docker-compose.yml")]
        return [(compose + ["build"], {"APP_VERSION": sha})]
    return [
        ([str(d / "backend/venv/bin/pip"), "install", "-r", str(d / "backend/requirements.txt")], {}),
        (["npm", "--prefix", str(d / "frontend"), "ci"], {}),
        (["npm", "--prefix", str(d / "frontend"), "run", "build"], {}),
    ]


def _apply_steps(m: str, d: Path, sha: str) -> list[tuple[list[str], dict]]:
    if m == "docker":
        # `up -d` replaces this very container, which would kill the command
        # half way. A detached helper container (docker CLI image) outlives it.
        # The app folder is mounted at the same path the host uses.
        return [
            (
                [
                    "docker", "run", "-d", "--rm",
                    "-v", "/var/run/docker.sock:/var/run/docker.sock",
                    "-v", f"{d}:{d}", "-w", str(d),
                    "-e", f"APP_VERSION={sha}",
                    DOCKER_CLI_IMAGE, "compose", "-f", str(d / "docker-compose.yml"), "up", "-d",
                ],
                {},
            )
        ]
    # Frontend first, backend last: restarting the backend ends this job's process.
    return [(["systemctl", "restart", u], {}) for u in SYSTEMD_UNITS[::-1]]


async def _job_main(target: str) -> None:
    assert _job is not None
    m, d = mode(), app_dir()
    prev = None
    try:
        await _run(["git", "fetch", "--quiet", "origin"], d)
        dirty = await _run(["git", "status", "--porcelain", "--untracked-files=no"], d)
        if dirty:
            raise StepFailed("the install has local changes to tracked files; refusing to overwrite them")
        prev = await _run(["git", "rev-parse", "HEAD"], d)
        await _run(["git", "cat-file", "-e", f"{target}^{{commit}}"], d)
        await _run(["git", "checkout", "--quiet", "--detach", target], d)
        for argv, env in _build_steps(m, d, target):
            await _run(argv, d, env)
        _job["status"] = "restarting"
        _log("New version built; restarting. This page reconnects when it is back.")
        for argv, env in _apply_steps(m, d, target):
            await _run(argv, d, env)
    except StepFailed as e:
        _job["status"], _job["error"] = "failed", str(e)
        _log(f"FAILED: {e}")
        if prev:
            await _rollback(m, d, prev)
        _save()
    except Exception as e:  # never leave the job 'running'
        _job["status"], _job["error"] = "failed", f"unexpected error ({type(e).__name__})"
        _log(f"FAILED: {_job['error']}")
        if prev:
            await _rollback(m, d, prev)
        _save()
    else:
        if _job["status"] == "restarting" and installed_version() == target:
            _job["status"] = "succeeded"
        _save()


async def _rollback(m: str | None, d: Path, prev: str) -> None:
    """Return the checkout to the old commit; the old version never stopped."""
    _log(f"Rolling back to {prev[:7]}; the old version keeps running.")
    try:
        await _run(["git", "checkout", "--quiet", "--detach", prev], d)
        if m == "systemd":
            for argv, env in _build_steps(m, d, prev):
                await _run(argv, d, env)
    except StepFailed as e:
        _log(f"Rollback step failed: {e}")


async def start_update() -> dict:
    """Start the job. Raises RuntimeError (busy / not configured) or the check's errors."""
    global _job, _task
    if not mode():
        raise RuntimeError("not_configured")

    # Fast-path: if another caller is already in the critical section (between
    # the busy check and the GitHub requests), reject immediately with 409.
    # This also avoids the "Lock is bound to a different event loop" error that
    # can happen when tests run in separate asyncio.run() loops.
    if _start_update_lock.locked():
        raise RuntimeError("busy")

    # Use a lock to prevent two concurrent callers from both passing the busy check
    # while the first is still awaiting check().
    async with _start_update_lock:
        cur = get_job()
        if cur and cur["status"] in ("running", "restarting") and _task and not _task.done():
            raise RuntimeError("busy")
        # Use fresh lookup for the update target - bypass cache
        installed = installed_version()
        try:
            latest = await _latest_version_fresh()
        except PermissionError:
            raise ConnectionError(
                "Cannot reach GitHub: access refused. Set GITHUB_TOKEN on the backend "
                "if the repository is private."
                if not os.environ.get("GITHUB_TOKEN")
                else "Cannot reach GitHub: the configured GITHUB_TOKEN was refused."
            )
        except LookupError as e:
            if str(e) == "rate_limit":
                raise ConnectionError(
                    "GitHub's request limit is used up; try again later or set GITHUB_TOKEN on the backend."
                )
            raise ConnectionError(f"Cannot reach GitHub ({type(e).__name__}).")
        except (httpx.HTTPError, ValueError) as e:
            raise ConnectionError(f"Cannot reach GitHub ({type(e).__name__}).")

        rel = await _relation(installed, latest["sha"])
        if rel == "equal":
            raise RuntimeError("up_to_date")
        if rel not in ("older", "diverged"):
            raise RuntimeError("up_to_date")

        target = latest["sha"]
        _job = {
            "status": "running",
            "target": target,
            "from": installed,
            "started_at": time.time(),
            "error": None,
            "log": [f"Updating {installed[:7]} -> {target[:7]} ({mode()})"],
        }
        _save()
        _task = asyncio.create_task(_job_main(target))
        return _job
