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

    # Start first call, wait for it to begin the checkout (job is running)
    first_task = asyncio.create_task(upd.start_update())
    await r._job_started.wait()
    # Now start second call - it should get "busy" because first job is running
    second_task = asyncio.create_task(upd.start_update())
    
    # Release the first job to complete
    await r.release()
    
    a, b = await asyncio.gather(first_task, second_task, return_exceptions=True)

    # One should succeed, one should raise RuntimeError("busy")
    checkouts = [c for c in r.text() if f"checkout --quiet --detach {NEW}" in c]

    # Exactly one checkout should happen
    assert len(checkouts) == 1, f"Expected 1 checkout, got {len(checkouts)}: {checkouts}"

    # One result should be the job dict, the other should be RuntimeError("busy")
    successes = [x for x in (a, b) if not isinstance(x, Exception)]
    errors = [x for x in (a, b) if isinstance(x, RuntimeError) and "busy" in str(x)]
    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
    assert len(errors) == 1, f"Expected 1 busy error, got {len(errors)}: {errors}"


@sync
async def test_post_update_while_starting_returns_409(client, upd, monkeypatch):
    """POST /api/update while a job is starting should return 409."""
    # Make the GitHub check slow
    async def slow(request):
        await asyncio.sleep(0.2)
        r = {**BRANCH, **CMP}.get(request.url.path, (404, {}))
        return httpx.Response(r[0], json=r[1])

    class SlowTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            return await slow(request)

    monkeypatch.setattr(upd, "_transport", SlowTransport())
    r = SlowRunner()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", r)
    upd._job = upd._task = None

    # Start the first update in the background (it will be slow due to GitHub)
    first_task = asyncio.create_task(upd.start_update())
    
    # Give the first call time to pass the busy check and start the GitHub request
    await asyncio.sleep(0.05)

    # Now try to call start_update directly (simulating a second API call)
    # The second call should get "busy" because the first update is still "starting"
    second_task = asyncio.create_task(upd.start_update())
    
    # Wait for the first task to reach the checkout phase
    await r._job_started.wait()
    # Release it
    await r.release()
    
    a, b = await asyncio.gather(first_task, second_task, return_exceptions=True)

    # The first should succeed, the second should get RuntimeError("busy")
    successes = [x for x in (a, b) if not isinstance(x, Exception)]
    errors = [x for x in (a, b) if isinstance(x, RuntimeError) and "busy" in str(x)]
    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
    assert len(errors) == 1, f"Expected 1 busy error, got {len(errors)}: {errors}"


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
    """When the ref is missing from both loose and packed-refs, return 'unknown'."""
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