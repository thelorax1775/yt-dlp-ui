"""POST /api/download end to end with the fake yt-dlp."""

import time

import pytest

URL = "https://example.com/watch?v=abc"


def wait_for_status(client, job_id, wanted, timeout=15.0):
    deadline = time.monotonic() + timeout
    job = None
    while time.monotonic() < deadline:
        jobs = {j["id"]: j for j in client.get("/api/jobs").json()}
        job = jobs.get(job_id)
        if job and job["status"] in wanted:
            return job
        time.sleep(0.05)
    pytest.fail(f"job {job_id} did not reach {wanted} in {timeout}s; last: {job}")


@pytest.mark.parametrize("url", ["ftp://example.com/x", "javascript:alert(1)", "example.com/x", ""])
def test_non_http_url_is_422(client, fake_ytdlp_calls, url):
    assert client.post("/api/download", json={"url": url}).status_code == 422
    assert client.get("/api/jobs").json() == []
    # only the settings page's --version probe may have run, never a download
    assert all(c == ["--version"] for c in fake_ytdlp_calls())


def test_download_finishes_and_lands_in_history(client, download_root, fake_ytdlp_calls):
    resp = client.post("/api/download", json={"url": URL})
    assert resp.status_code == 200
    job_id = resp.json()["id"]

    job = wait_for_status(client, job_id, {"finished", "failed", "error"})
    assert job["status"] == "finished", job
    assert job["file_path"].startswith(download_root)
    assert job["file_path"].endswith("Fake Title.mp4")

    history = client.get("/api/history").json()
    assert len(history) == 1
    assert history[0]["url"] == URL
    assert history[0]["file_path"] == job["file_path"]

    # the app really ran the fake, with the URL last
    runs = [c for c in fake_ytdlp_calls() if URL in c]
    assert runs and runs[-1][-1] == URL


def test_bestaudio_download_makes_audio_file(client, fake_ytdlp_calls):
    job_id = client.post("/api/download", json={"url": URL, "format_id": "bestaudio"}).json()["id"]
    job = wait_for_status(client, job_id, {"finished", "failed", "error"})
    assert job["status"] == "finished", job
    assert job["file_path"].endswith(".mp3")


def test_failing_download_is_not_in_history(client):
    job_id = client.post("/api/download", json={"url": "https://example.com/fail"}).json()["id"]
    job = wait_for_status(client, job_id, {"finished", "failed", "error"})
    assert job["status"] != "finished"
    assert job["error"]
    assert client.get("/api/history").json() == []
