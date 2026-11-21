"""Tests for rate limit handling and caching in updater.py."""

import asyncio
import time

from tests.test_update import sync, OLD, NEW, BRANCH, github, upd


CMP = {f"/repos/thelorax1775/yt-dlp-ui/compare/{OLD}...{NEW}": (200, {"status": "ahead"})}
RATE_LIMIT_MSG = "GitHub's request limit is used up; try again later or set GITHUB_TOKEN on the backend."


@sync
async def test_rate_limit_403_with_header_returns_unreachable(upd, monkeypatch):
    """A 403 with x-ratelimit-remaining: 0 gives state 'unreachable' and exact rate-limit message."""
    routes = {
        "/repos/thelorax1775/yt-dlp-ui/releases/latest": (
            403,
            {"message": "API rate limit exceeded"},
            {"x-ratelimit-remaining": "0"},
        )
    }
    github(monkeypatch, upd, routes)
    r = await upd.check()
    assert r["state"] == "unreachable"
    assert r["message"] == RATE_LIMIT_MSG
    assert "private" not in r["message"].lower()


@sync
async def test_rate_limit_429_returns_unreachable(upd, monkeypatch):
    """A 429 gives the same rate-limit message."""
    routes = {
        "/repos/thelorax1775/yt-dlp-ui/releases/latest": (
            429,
            {"message": "API rate limit exceeded"},
            {"x-ratelimit-remaining": "0"},
        )
    }
    github(monkeypatch, upd, routes)
    r = await upd.check()
    assert r["state"] == "unreachable"
    assert r["message"] == RATE_LIMIT_MSG
    assert "private" not in r["message"].lower()


@sync
async def test_403_without_ratelimit_header_still_says_private(upd, monkeypatch):
    """A 403 without the header still gives the existing 'private' message."""
    routes = {
        "/repos/thelorax1775/yt-dlp-ui/releases/latest": (
            403,
            {"message": "Forbidden"},
        )
    }
    github(monkeypatch, upd, routes)
    r = await upd.check()
    assert r["state"] == "unreachable"
    assert "GITHUB_TOKEN" in r["message"]
    assert "private" in r["message"].lower()


@sync
async def test_check_caches_latest_version_and_relation(upd, monkeypatch):
    """Two check() calls within cache window make 3 GitHub requests total (both fully cached)."""
    routes = {**BRANCH, **CMP}
    seen = github(monkeypatch, upd, routes)

    # First call - 3 requests: releases/latest, commits/HEAD, compare
    r1 = await upd.check()
    assert r1["state"] == "update_available"

    # Second call within cache window - 0 requests (both latest_version and relation cached)
    r2 = await upd.check()
    assert r2["state"] == "update_available"

    # Should have made 3 requests total (not 6 which would be 3 per call without caching)
    assert len(seen) == 3, f"Expected 3 requests, got {len(seen)}"


@sync
async def test_cache_expires_after_600_seconds(upd, monkeypatch):
    """After advancing monotonic clock past 600s, a third call makes requests again."""
    routes = {**BRANCH, **CMP}
    seen = github(monkeypatch, upd, routes)

    # First call - 3 requests
    r1 = await upd.check()
    assert r1["state"] == "update_available"

    # Second call within cache window - 0 requests
    r2 = await upd.check()
    assert r2["state"] == "update_available"
    assert len(seen) == 3

    # Advance time by 601 seconds by patching time.monotonic in the updater module
    import services.updater as updater_module
    base_time = time.monotonic()
    monkeypatch.setattr(updater_module.time, "monotonic", lambda: base_time + 601)

    r3 = await upd.check()
    assert r3["state"] == "update_available"

    # Should have made 6 requests total (3 + 0 + 3)
    assert len(seen) == 6, f"Expected 6 requests after cache expiry, got {len(seen)}"


@sync
async def test_start_update_does_not_use_cache(upd, monkeypatch):
    """start_update() makes fresh GitHub requests for /releases/latest and /commits/HEAD even when cache is fresh."""
    routes = {**BRANCH, **CMP}
    seen = github(monkeypatch, upd, routes)

    # First populate cache via check()
    await upd.check()
    initial_count = len(seen)
    assert initial_count == 3

    # Now call start_update() - it should NOT use the cache
    # Mock subprocess to avoid actual commands
    class Runner:
        def __init__(self):
            self.calls = []

        async def __call__(self, *args, **kwargs):
            argv = list(args)
            self.calls.append((argv, kwargs.get("env") or {}))
            text = " ".join(argv)

            class P:
                returncode = 0

                async def communicate(_):
                    if "rev-parse HEAD" in text:
                        return OLD.encode(), b""
                    if "status --porcelain" in text:
                        return b"", b""
                    return b"", b""

            return P()

    runner = Runner()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", runner)

    # start_update() calls check() internally but should bypass cache via check(fresh=True)
    job = await upd.start_update()

    # start_update() should have made fresh GitHub requests
    # Check that /releases/latest and /commits/HEAD were requested again
    paths = [str(req.url.path) for req in seen[initial_count:]]
    assert "/repos/thelorax1775/yt-dlp-ui/releases/latest" in paths, \
        f"Expected /releases/latest in fresh requests, got {paths}"
    assert "/repos/thelorax1775/yt-dlp-ui/commits/HEAD" in paths, \
        f"Expected /commits/HEAD in fresh requests, got {paths}"
    
    # The job should be running with the new commit as target
    assert job["status"] == "running"
    assert job["target"] == NEW


@sync
async def test_cache_clear_function_clears_both_caches(upd, monkeypatch):
    """_cache_clear() function clears both latest_version and relation caches."""
    routes = {**BRANCH, **CMP}
    seen = github(monkeypatch, upd, routes)

    # First call - 3 requests
    await upd.check()
    assert len(seen) == 3

    # Second call - 0 requests (cached)
    await upd.check()
    assert len(seen) == 3

    # Clear cache
    upd._cache_clear()

    # Third call - should make 3 requests again
    await upd.check()
    assert len(seen) == 6, f"Expected 6 requests after cache clear, got {len(seen)}"


@sync
async def test_rate_limit_on_compare_returns_rate_limit_message(upd, monkeypatch):
    """A rate-limited compare request returns the rate-limit message, not 'unknown'."""
    routes = {
        "/repos/thelorax1775/yt-dlp-ui/releases/latest": (200, {"tag_name": "v2.0.0"}),
        "/repos/thelorax1775/yt-dlp-ui/commits/v2.0.0": (200, {"sha": NEW}),
        f"/repos/thelorax1775/yt-dlp-ui/compare/{OLD}...{NEW}": (
            403,
            {"message": "API rate limit exceeded"},
            {"x-ratelimit-remaining": "0"},
        ),
    }
    seen = github(monkeypatch, upd, routes)
    r = await upd.check()
    assert r["state"] == "unreachable"
    assert r["message"] == RATE_LIMIT_MSG
    assert "private" not in r["message"].lower()
    assert "unknown" not in r["message"].lower()
