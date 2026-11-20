"""Download queue: cancel/retry, restart recovery, stuck lookups.

A small shell script named ``yt-dlp-fake`` in tmp_path really runs (see the
``real_program`` fixture); yt-dlp itself never does and nothing uses the network.
"""

import os
import sqlite3
import time
from datetime import datetime

import pytest

URL = "https://example.invalid/watch?v="


def write_script(path, body):
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return path


@pytest.fixture
def fake_ytdlp(backend, client, downloads_dir, real_program):
    """Install a fake yt-dlp. Returns (script, runs_file, gate_file).

    Download runs append a line to runs_file and wait until gate_file exists.
    Lookups (--dump-single-json) answer at once.
    """
    runs = backend.tmp_path / "runs.txt"
    gate = backend.tmp_path / "gate"
    script = write_script(
        backend.tmp_path / "yt-dlp-fake",
        f"""case "$*" in
*--version*) echo 1.0; exit 0;;
*--dump-single-json*) echo '{{"title": "T"}}'; exit 0;;
esac
for last; do :; done
echo "$last" >> {runs}
while [ ! -e {gate} ]; do sleep 0.05; done
echo "OUTPATH {downloads_dir}/out.mp4"
""",
    )
    real_program(script)
    response = client.post("/api/settings", json={"ytdlp_path": str(script)})
    assert response.status_code == 200, response.text
    yield script, runs, gate
    gate.touch()  # never leave a fake download waiting


def run_count(runs):
    return len(runs.read_text().split()) if runs.exists() else 0


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition not reached in time")


def test_cancel_then_retry_of_a_queued_job_runs_it_once(
    client, backend, fake_ytdlp, wait_for_job, wait_for_download, db
):
    _, runs, gate = fake_ytdlp
    ids = [
        client.post("/api/download", json={"url": URL + str(n)}).json()["id"] for n in range(3)
    ]
    # Two workers are busy with jobs 0 and 1; job 2 is still waiting.
    wait_until(lambda: run_count(runs) == 2)
    assert client.delete(f"/api/jobs/{ids[2]}").status_code == 200
    assert client.post(f"/api/jobs/{ids[2]}/retry").status_code == 200

    gate.touch()
    for job_id in ids:
        wait_for_download(job_id)

    jobs = {j["id"]: j for j in client.get("/api/jobs").json()}
    assert [jobs[i]["status"] for i in ids] == ["finished"] * 3
    assert run_count(runs) == 3
    history_ids = [row[0] for row in db("SELECT id FROM history")]
    assert sorted(history_ids) == sorted(ids)


def test_writing_history_twice_does_not_fail(backend, client, db):
    dm = backend.download_manager
    job = dm.Job(url=URL + "x", format_id=None)
    portal = client.portal
    portal.call(dm.manager._write_history, job)
    portal.call(dm.manager._write_history, job)
    assert len(db("SELECT id FROM history")) == 1


def insert_job(path, job_id, status):
    now = datetime.utcnow().isoformat(sep=" ")
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO jobs (id, url, title, status, progress, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, 12.5, ?, ?)",
            (job_id, URL + job_id, "t-" + job_id, status, now, now),
        )


def test_jobs_survive_a_restart(backend, fake_ytdlp, db, wait_for_job):
    from fastapi.testclient import TestClient

    _, runs, gate = fake_ytdlp
    for status in ("queued", "downloading", "finished", "failed"):
        insert_job(backend.db_path, status, status)

    # A new process: freshly imported modules on the same database file.
    from tests.conftest import _purge_app_modules

    _purge_app_modules()
    import main
    from models import database

    with TestClient(main.app) as second:
        jobs = {j["id"]: j for j in second.get("/api/jobs").json()}
        assert set(jobs) == {"queued", "downloading", "finished", "failed"}
        for job_id in ("queued", "downloading"):
            assert jobs[job_id]["status"] == "failed"
            assert jobs[job_id]["error"] == "interrupted by restart"
        assert jobs["finished"]["status"] == "finished"
        assert jobs["failed"]["status"] == "failed"
        # Nothing was started on its own.
        time.sleep(0.3)
        assert run_count(runs) == 0

        # The marking is saved, and a failed job can be retried.
        assert second.post("/api/jobs/queued/retry").status_code == 200
        gate.touch()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status = {j["id"]: j["status"] for j in second.get("/api/jobs").json()}["queued"]
            if status == "finished":
                break
            time.sleep(0.02)
        assert status == "finished"
        assert run_count(runs) == 1
        second.portal.call(database.engine.dispose)
    rows = dict(db("SELECT id, status FROM jobs"))
    assert rows["downloading"] == "failed"


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False


@pytest.fixture
def hanging_ytdlp(backend, client, downloads_dir, real_program):
    pidfile = backend.tmp_path / "lookup.pid"
    script = write_script(
        backend.tmp_path / "yt-dlp-hang",
        f"""case "$*" in *--dump-single-json*) ;; *) echo 1.0; exit 0;; esac
echo $$ > {pidfile}
exec sleep 1000
""",
    )
    real_program(script)
    assert client.post("/api/settings", json={"ytdlp_path": str(script)}).status_code == 200
    return pidfile


def test_cancel_kills_a_stuck_lookup(client, hanging_ytdlp, wait_for_job):
    job_id = client.post("/api/download", json={"url": URL + "hang"}).json()["id"]
    wait_until(lambda: hanging_ytdlp.exists() and hanging_ytdlp.read_text().strip())
    pid = int(hanging_ytdlp.read_text())
    assert alive(pid)

    started = time.monotonic()
    assert client.delete(f"/api/jobs/{job_id}").status_code == 200
    assert time.monotonic() - started < 5
    wait_until(lambda: not alive(pid), timeout=5)
    assert wait_for_job(job_id)["status"] == "cancelled"


def test_lookup_timeout_fails_the_job_and_frees_the_worker(
    client, backend, hanging_ytdlp, monkeypatch, wait_for_job
):
    from services import metadata

    monkeypatch.setattr(metadata, "LOOKUP_TIMEOUT_SECONDS", 1)
    job_id = client.post("/api/download", json={"url": URL + "hang"}).json()["id"]
    wait_until(lambda: hanging_ytdlp.exists() and hanging_ytdlp.read_text().strip())
    pid = int(hanging_ytdlp.read_text())

    job = wait_for_job(job_id, timeout=6)
    assert job["status"] == "failed"
    assert "timed out" in job["error"]
    assert not alive(pid)

    # The worker is free again: a second job is picked up (and times out too).
    second = client.post("/api/download", json={"url": URL + "again"}).json()["id"]
    assert wait_for_job(second, timeout=6)["status"] == "failed"


def test_info_lookup_times_out(client, hanging_ytdlp, monkeypatch):
    from services import metadata

    monkeypatch.setattr(metadata, "LOOKUP_TIMEOUT_SECONDS", 1)
    response = client.get("/api/info", params={"url": URL + "hang"})
    assert response.status_code == 400
    assert "timed out" in response.json()["detail"]
