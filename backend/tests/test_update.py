"""Update check, update job (commands mocked) and the admin check."""

import asyncio
import functools
import time

import httpx
import pytest

def sync(fn):
    """No pytest-asyncio here: run an async test on its own loop."""

    @functools.wraps(fn)
    def wrapper(*a, **k):
        return asyncio.run(fn(*a, **k))

    return wrapper


OLD = "a" * 40
NEW = "b" * 40


@pytest.fixture
def upd(backend, monkeypatch):
    from services import updater

    monkeypatch.setenv("APP_VERSION", OLD)
    monkeypatch.setenv("UPDATE_MODE", "systemd")
    monkeypatch.setenv("UPDATE_ADMIN_TOKEN", "s3cret-admin")
    monkeypatch.setenv("UPDATE_APP_DIR", str(backend.tmp_path / "app"))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    (backend.tmp_path / "app").mkdir()
    return updater


def github(monkeypatch, upd, routes):
    """routes: path -> (status, json) or (status, json, headers) or an exception instance."""
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        r = routes.get(request.url.path)
        if isinstance(r, Exception):
            raise r
        if r is None:
            return httpx.Response(404, json={})
        if len(r) == 3:
            return httpx.Response(r[0], json=r[1], headers=r[2])
        return httpx.Response(r[0], json=r[1])

    monkeypatch.setattr(upd, "_transport", httpx.MockTransport(handler))
    return seen


BRANCH = {
    "/repos/thelorax1775/yt-dlp-ui/releases/latest": (404, {}),
    "/repos/thelorax1775/yt-dlp-ui/commits/HEAD": (200, {"sha": NEW}),
}


# ---- version compare ----


@pytest.mark.parametrize(
    "installed,latest,expected",
    [
        ("1.2.3", "1.3.0", "older"),
        ("v1.10.0", "1.9.9", "newer"),
        ("v1.2.3", "1.2.3", "equal"),
        (OLD, OLD, "equal"),
        (OLD[:7], OLD, "equal"),
        (OLD, NEW, "unknown"),
        ("unknown", NEW, "unknown"),
    ],
)
def test_compare_versions(upd, installed, latest, expected):
    assert upd.compare_versions(installed, latest) == expected


@sync
async def test_check_older_equal_newer_by_sha(upd, monkeypatch):
    routes = dict(BRANCH)
    routes[f"/repos/thelorax1775/yt-dlp-ui/compare/{OLD}...{NEW}"] = (200, {"status": "ahead"})
    github(monkeypatch, upd, routes)
    r = await upd.check()
    assert (r["state"], r["update_available"]) == ("update_available", True)
    assert r["installed"] == OLD and r["latest"]["sha"] == NEW

    monkeypatch.setenv("APP_VERSION", NEW)
    r = await upd.check()
    assert (r["state"], r["update_available"]) == ("up_to_date", False)

    routes[f"/repos/thelorax1775/yt-dlp-ui/compare/{OLD}...{NEW}"] = (200, {"status": "behind"})
    monkeypatch.setenv("APP_VERSION", OLD)
    r = await upd.check()
    assert (r["state"], r["update_available"]) == ("ahead", False)


@sync
async def test_check_uses_latest_release_when_there_is_one(upd, monkeypatch):
    base = "/repos/thelorax1775/yt-dlp-ui"
    github(monkeypatch, upd, {
        f"{base}/releases/latest": (200, {"tag_name": "v2.0.0"}),
        f"{base}/commits/v2.0.0": (200, {"sha": NEW}),
        f"{base}/compare/{OLD}...{NEW}": (200, {"status": "ahead"}),
    })
    r = await upd.check()
    assert r["latest"] == {"kind": "release", "label": "v2.0.0", "sha": NEW}
    assert r["update_available"] is True


# ---- no token / unreachable ----


@sync
async def test_private_repo_without_token_says_it_cannot_reach_github(upd, monkeypatch):
    seen = github(monkeypatch, upd, {"/repos/thelorax1775/yt-dlp-ui/releases/latest": (403, {})})
    r = await upd.check()
    assert r["state"] == "unreachable" and "Cannot reach GitHub" in r["message"]
    assert "GITHUB_TOKEN" in r["message"]
    assert r["update_available"] is False
    assert "authorization" not in seen[0].headers


@sync
async def test_network_error_is_reported_not_raised(upd, monkeypatch):
    github(monkeypatch, upd, {
        "/repos/thelorax1775/yt-dlp-ui/releases/latest": httpx.ConnectError("boom"),
    })
    r = await upd.check()
    assert r["state"] == "unreachable" and r["latest"] is None


@sync
async def test_token_is_sent_to_github_but_never_returned(upd, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_supersecret")
    seen = github(monkeypatch, upd, {"/repos/thelorax1775/yt-dlp-ui/releases/latest": (401, {})})
    r = await upd.check()
    assert seen[0].headers["authorization"] == "Bearer ghp_supersecret"
    assert "ghp_supersecret" not in str(r)
    assert r["token_configured"] is True


# ---- the job ----


class Runner:
    """Replaces asyncio.create_subprocess_exec; records argv, can fail a step."""

    def __init__(self, fail_on=None, dirty=False):
        self.calls, self.fail_on, self.dirty = [], fail_on, dirty

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

        class P:
            returncode = rc

            async def communicate(_):
                return out, b""

        return P()

    def text(self):
        return [" ".join(a) for a, _ in self.calls]


async def run_job(upd, monkeypatch, runner):
    monkeypatch.setattr(asyncio, "create_subprocess_exec", runner)
    github(monkeypatch, upd, {**BRANCH, f"/repos/thelorax1775/yt-dlp-ui/compare/{OLD}...{NEW}": (200, {"status": "ahead"})})
    upd._job = upd._task = None
    await upd.start_update()
    await upd._task
    return upd.get_job()


@sync
async def test_job_success_runs_expected_commands(upd, monkeypatch):
    r = Runner()
    job = await run_job(upd, monkeypatch, r)
    cmds = r.text()
    assert job["status"] == "restarting"  # still the old process until the restart lands
    assert any(c.endswith(f"checkout --quiet --detach {NEW}") for c in cmds)
    assert any("pip install -r" in c for c in cmds)
    assert any("npm --prefix" in c and "build" in c for c in cmds)
    assert cmds[-2:] == ["systemctl restart ytdlp-frontend", "systemctl restart ytdlp-backend"]
    # checkout happens before build, build before restart
    idx = lambda s: next(i for i, c in enumerate(cmds) if s in c)
    assert idx("checkout") < idx("pip install") < idx("systemctl")
    # secrets never reach the subprocess environment
    assert all("UPDATE_ADMIN_TOKEN" not in env and "GITHUB_TOKEN" not in env for _, env in r.calls)
    assert "s3cret-admin" not in str(job)


@sync
async def test_job_restart_on_new_version_is_marked_succeeded(upd, monkeypatch):
    await run_job(upd, monkeypatch, Runner())
    monkeypatch.setenv("APP_VERSION", NEW)
    upd._job = None  # new process reads the saved file
    upd.resolve_after_restart()
    assert upd.get_job()["status"] == "succeeded"


@sync
async def test_failing_build_keeps_old_version_running(upd, monkeypatch):
    r = Runner(fail_on="npm --prefix")
    job = await run_job(upd, monkeypatch, r)
    cmds = r.text()
    assert job["status"] == "failed" and "failed" in job["error"]
    assert not any(c.startswith("systemctl") for c in cmds)  # never restarted
    assert cmds[-1].endswith(f"checkout --quiet --detach {OLD}") or any(
        c.endswith(f"checkout --quiet --detach {OLD}") for c in cmds
    )
    assert any("Rolling back" in line for line in job["log"])


@sync
async def test_local_changes_stop_the_update_before_checkout(upd, monkeypatch):
    r = Runner(dirty=True)
    job = await run_job(upd, monkeypatch, r)
    assert job["status"] == "failed" and "local changes" in job["error"]
    assert not any("checkout" in c for c in r.text())


@sync
async def test_docker_mode_builds_then_restarts_via_helper_container(upd, monkeypatch):
    monkeypatch.setenv("UPDATE_MODE", "docker")
    r = Runner()
    await run_job(upd, monkeypatch, r)
    cmds = r.text()
    build = next(c for c in cmds if " compose" in c and c.endswith(" build"))
    up = next(c for c in cmds if c.startswith("docker run -d --rm"))
    assert cmds.index(build) < cmds.index(up)
    assert {"APP_VERSION": NEW}.items() <= next(e for a, e in r.calls if " ".join(a) == build).items()


@sync
async def test_no_shell_and_target_comes_only_from_github(upd, monkeypatch):
    r = Runner()
    await run_job(upd, monkeypatch, r)
    for argv, _ in r.calls:
        assert argv[0] in {"git", "npm", "systemctl", "docker"} or argv[0].endswith("/pip")
        assert all(isinstance(a, str) for a in argv)
    assert "sh" not in {a[0] for a, _ in r.calls}


# ---- HTTP + permission ----


def test_update_needs_the_admin_token(client, upd, monkeypatch):
    runner = Runner()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", runner)
    github(monkeypatch, upd, BRANCH)
    assert client.post("/api/update").status_code == 403
    assert client.post("/api/update", headers={"X-Admin-Token": "nope"}).status_code == 403
    assert runner.calls == []
    assert upd.get_job() is None


def test_update_is_disabled_without_configured_token(client, upd, monkeypatch):
    monkeypatch.delenv("UPDATE_ADMIN_TOKEN")
    r = client.post("/api/update", headers={"X-Admin-Token": ""})
    assert r.status_code == 403 and "disabled" in r.json()["detail"]


def test_cross_site_post_without_the_header_is_refused(client, upd):
    r = client.post("/api/update", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    pre = client.options("/api/update", headers={
        "Origin": "https://evil.example",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "x-admin-token",
    })
    assert "access-control-allow-origin" not in pre.headers


def test_update_endpoint_with_token_starts_job_and_status_is_pollable(client, upd, monkeypatch):
    monkeypatch.setattr(asyncio, "create_subprocess_exec", Runner())
    github(monkeypatch, upd, {**BRANCH, f"/repos/thelorax1775/yt-dlp-ui/compare/{OLD}...{NEW}": (200, {"status": "ahead"})})
    r = client.post("/api/update", headers={"X-Admin-Token": "s3cret-admin"}, json={"ref": "; rm -rf /"})
    assert r.status_code == 202, r.text
    assert r.json()["job"]["target"] == NEW  # body is ignored
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = client.get("/api/update/status").json()["job"]
        if job["status"] != "running":
            break
        time.sleep(0.02)
    assert job["status"] == "restarting" and job["log"]
    check = client.get("/api/update/check").json()
    assert check["installed"] == OLD and "s3cret-admin" not in str(check)


def test_up_to_date_cannot_be_updated(client, upd, monkeypatch):
    monkeypatch.setenv("APP_VERSION", NEW)
    github(monkeypatch, upd, BRANCH)
    r = client.post("/api/update", headers={"X-Admin-Token": "s3cret-admin"})
    assert r.status_code == 409
