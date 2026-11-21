"""Tests for the race condition in start_update and packed-refs handling in installed_version."""

import asyncio
import subprocess
import httpx
import pytest

from tests.test_update import sync, OLD, NEW, BRANCH, Runner, github, upd  # noqa: F401

CMP = {f"/repos/thelorax1775/yt-dlp-ui/compare/{OLD}...{NEW}": (200, {"status": "ahead"})}


# ---- Race condition tests ----

class SlowRunner:
    """Runner that makes the background job stay in 'running' state."""

    def __init__(self, fail_on=None, dirty=False):
        self.calls, self.fail_on, self.dirty = [], fail_on, dirty
        self._job_started = asyncio.Event()
        self._release_job = asyncio.Event()

    async def __call__(self, *args, **kwargs):
        argv = list(args)
        self.calls.append((argv, kwargs.get("env") or {}))
        text = " ".join(argv)
        rc = 1 if self.fail_on and self.fail_on in text else 0
        out = b""
        if "status --porcelain" in text and self.dirty:
            out = b" M backend/main.py\n"
        if "rev-parse HEAD" in text:
            out = OLD.encode()
        if "cat-file -e" in text:
            # Verify commit exists - succeed
            out = b""
        if "checkout --quiet --detach" in text:
            # Signal that the job has started the checkout phase
            self._job_started.set()
            # Wait until released (simulates long build/restart)
            await self._release_job.wait()
            self._job_started.clear()

        class P:
            returncode = rc

            async def communicate(_):
                return out, b""

        return P()

    def text(self):
        return [" ".join(a) for a, _ in self.calls]

    async def release(self):
        """Release the job to complete."""
        self._release_job.set()


@sync
async def test_two_concurrent_start_update_calls_only_one_job(upd, monkeypatch):
    """Two concurrent start_update() calls: only one should proceed, the other raises RuntimeError('busy')."""
    async def slow(request):
        await asyncio.sleep(0.2)
        r = {**BRANCH, **CMP}.get(request.url.path, (404, {}))
        return httpx.Response(r[0], json=r[1])

    class SlowTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return await slow(request)

    r = SlowRunner()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", r)
    monkeypatch.setattr(upd, "_transport", SlowTransport())
    upd._job = upd._task = None

    # Start BOTH calls concurrently while the first is still in check()
    # This tests the race condition: both callers enter start_update() at the same time
    a, b = await asyncio.gather(upd.start_update(), upd.start_update(), return_exceptions=True)

    # Release the job if it got that far
    await r.release()

    # Exactly one checkout should happen
    checkouts = [c for c in r.text() if f"checkout --quiet --detach {NEW}" in c]
    assert len(checkouts) == 1, f"Expected 1 checkout, got {len(checkouts)}: {checkouts}"

    # One result should be the job dict, the other should be RuntimeError("busy")
    successes = [x for x in (a, b) if not isinstance(x, Exception)]
    errors = [x for x in (a, b) if isinstance(x, RuntimeError) and "busy" in str(x)]
    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
    assert len(errors) == 1, f"Expected 1 busy error, got {len(errors)}: {errors}"


@sync
async def test_post_update_while_starting_returns_409(backend, upd, monkeypatch):
    """POST /api/update while a job is starting should return 409.

    Uses httpx.AsyncClient with ASGITransport so both requests run on the
    same event loop (the pytest loop), avoiding the TestClient's separate thread.
    """
    from httpx import ASGITransport, AsyncClient

    # Make the GitHub check slow
    async def slow(request):
        await asyncio.sleep(0.2)
        r = {**BRANCH, **CMP}.get(request.url.path, (404, {}))
        return httpx.Response(r[0], json=r[1])

    class SlowTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return await slow(request)

    r = SlowRunner()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", r)
    monkeypatch.setattr(upd, "_transport", SlowTransport())
    upd._job = upd._task = None

    # Use AsyncClient with ASGITransport to run on the same event loop
    transport = ASGITransport(app=backend.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Start the first update in the background (it will be slow due to GitHub)
        first_task = asyncio.create_task(upd.start_update())

        # Give the first call time to pass the busy check and start the GitHub request
        await asyncio.sleep(0.05)

        # Now make a real POST /api/update request through the app
        # It should get 409 because the first update is still "starting"
        response = await ac.post("/api/update", headers={"X-Admin-Token": "s3cret-admin"})

        # Release the first job to complete
        await r._job_started.wait()
        await r.release()

        # Wait for the first task to complete
        await first_task

    # The second POST should return 409 with the "already running" message
    assert response.status_code == 409, f"Expected 409, got {response.status_code}: {response.text}"
    assert "An update is already running" in response.json()["detail"]


# ---- Packed refs tests ----

def test_installed_version_with_packed_refs(upd, monkeypatch, tmp_path):
    """installed_version() should read from .git/packed-refs when loose ref is missing."""
    monkeypatch.delenv("APP_VERSION", raising=False)
    d = tmp_path / "repo"
    d.mkdir()

    run = lambda *a: subprocess.run(
        ["git", "-C", str(d), *a], check=True, capture_output=True, text=True
    ).stdout.strip()

    run("init", "-q", "-b", "main")
    run("-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "x")

    monkeypatch.setenv("UPDATE_APP_DIR", str(d))

    # Before pack-refs: should work via loose ref
    expected_sha = run("rev-parse", "HEAD")
    assert upd.installed_version() == expected_sha

    # After pack-refs: loose ref file is gone, should read from packed-refs
    run("pack-refs", "--all")
    # The loose ref file no longer exists
    assert not (d / ".git" / "refs" / "heads" / "main").exists()
    # packed-refs should have the ref
    packed = (d / ".git" / "packed-refs").read_text()
    assert f"{expected_sha} refs/heads/main" in packed

    # installed_version should still return the SHA
    assert upd.installed_version() == expected_sha


def test_installed_version_missing_from_both_returns_unknown(upd, monkeypatch, tmp_path):
    """When the ref is missing from both loose and packed-refs, return 'unknown'.

    This is a regression guard - main already returns 'unknown' in this case.
    It passes on both main and the fix branch.
    """
    monkeypatch.delenv("APP_VERSION", raising=False)
    d = tmp_path / "repo"
    d.mkdir()

    run = lambda *a: subprocess.run(
        ["git", "-C", str(d), *a], check=True, capture_output=True, text=True
    ).stdout.strip()

    run("init", "-q", "-b", "main")
    run("-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "x")

    monkeypatch.setenv("UPDATE_APP_DIR", str(d))

    # Remove both loose ref and packed-refs entry for main
    # (This simulates a corrupted repo or an orphaned HEAD)
    (d / ".git" / "HEAD").write_text("ref: refs/heads/nonexistent\n")
    run("pack-refs", "--all")  # This won't add the nonexistent ref

    # Should return "unknown" since neither place has the ref
    assert upd.installed_version() == "unknown"
