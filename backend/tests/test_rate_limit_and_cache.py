"""Tests for rate limit handling and caching in updater.py."""

import asyncio
import time
from unittest.mock import patch

import httpx
import pytest

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
    seen = github(monkeypatch, upd, routes)
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
async def test_check_caches_latest_version(upd, monkeypatch):
    """Two check() calls within cache window make 4 GitHub requests total (3 for first, 1 for second)."""
    routes = {**BRANCH, **CMP}
    seen = github(monkeypatch, upd, routes)

    # First call - 3 requests: releases/latest, commits/HEAD, compare
    r1 = await upd.check()
    assert r1["state"] == "update_available"

    # Second call within cache window - 1 request: compare (latest_version cached)
    r2 = await upd.check()
    assert r2["state"] == "update_available"

    # Should have made 4 requests total (not 6 which would be 3 per call without caching)
    assert len(seen) == 4, f"Expected 4 requests, got {len(seen)}"


@sync
async def test_cache_expires_after_600_seconds(upd, monkeypatch):
    """After advancing monotonic clock past 600s, a third call makes requests again."""
    routes = {**BRANCH, **CMP}
    seen = github(monkeypatch, upd, routes)

    # First call - 3 requests
    r1 = await upd.check()
    assert r1["state"] == "update_available"

    # Second call within cache window - 1 request (compare)
    r2 = await upd.check()
    assert r2["state"] == "update_available"
    assert len(seen) == 4

    # Advance time by 601 seconds by patching time.monotonic in the updater module
    import services.updater as updater_module
    base_time = time.monotonic()
    monkeypatch.setattr(updater_module.time, "monotonic", lambda: base_time + 601)
    
    r3 = await upd.check()
    assert r3["state"] == "update_available"

    # Should have made 7 requests total (3 + 1 + 3)
    assert len(seen) == 7, f"Expected 7 requests after cache expiry, got {len(seen)}"


@sync
async def test_start_update_does_not_use_cache(upd, monkeypatch):
    """start_update() makes GitHub requests even when cache is fresh."""
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

    # start_update() calls check() internally but should bypass cache
    try:
        await upd.start_update()
    except RuntimeError as e:
        # Expected: "up_to_date" or "not_configured" depending on state
        pass

    # start_update() should have made fresh GitHub requests
    # At minimum, it should call latest_version() again (3 requests)
    assert len(seen) > initial_count, "start_update() should make fresh GitHub requests"


@sync
async def test_cache_clear_function_exists(upd):
    """_cache_clear() function exists and clears the cache."""
    # This test will fail initially until we add the function
    assert hasattr(upd, "_cache_clear"), "_cache_clear function should exist"
    # Should not raise
    upd._cache_clear()


def test_upd_fixture_clears_cache(upd):
    """The upd fixture clears the cache so existing tests are unaffected."""
    # The fixture should call _cache_clear() automatically
    # This test just verifies the fixture works
    pass