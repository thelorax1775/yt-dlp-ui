"""Timestamp serialization tests.

Every datetime the API returns must carry a UTC offset (\"+00:00\" or \"Z\")
so the frontend can display the correct local time. This test proves that:

* The pydantic models serialize datetimes with a UTC offset.
* Files get their mtime from the filesystem in UTC.
* A naive datetime stored in the DB is serialized as UTC.
"""

import os
from datetime import datetime, timezone

import pytest


@pytest.mark.asyncio
async def test_history_finished_at_has_utc_offset(client, backend, downloads_dir, wait_for_download):
    """After a finished download, GET /api/history returns finished_at ending in +00:00 or Z."""
    final_path = str(downloads_dir / "Fake Title.mp4")
    backend.subprocess.download_lines = [
        "[download] Destination: " + final_path,
        "PROGRESS downloading  50.0% 1.00MiB/s 00:02",
        "PROGRESS downloading 100.0% 1.00MiB/s 00:00",
        "OUTPATH " + final_path,
    ]
    url = "https://example.invalid/watch?v=abc"

    response = client.post("/api/download", json={"url": url, "format_id": "bestaudio"})
    assert response.status_code == 200
    queued = response.json()

    job = wait_for_download(queued["id"])

    history = client.get("/api/history").json()
    assert len(history) == 1
    finished_at = history[0]["finished_at"]
    assert finished_at is not None
    # Must end with +00:00 or Z
    assert finished_at.endswith(("+00:00", "Z")), f"finished_at={finished_at!r}"

    # Parse it back and verify it's within 60s of now (UTC)
    parsed = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
    assert parsed.tzinfo == timezone.utc
    now_utc = datetime.now(timezone.utc)
    assert abs((parsed - now_utc).total_seconds()) < 60


@pytest.mark.asyncio
async def test_jobs_created_updated_at_have_utc_offset(client, backend, downloads_dir, wait_for_download):
    """GET /api/jobs returns created_at and updated_at with +00:00 or Z."""
    final_path = str(downloads_dir / "Fake Title.mp4")
    backend.subprocess.download_lines = [
        "[download] Destination: " + final_path,
        "PROGRESS downloading  50.0% 1.00MiB/s 00:02",
        "PROGRESS downloading 100.0% 1.00MiB/s 00:00",
        "OUTPATH " + final_path,
    ]
    url = "https://example.invalid/watch?v=abc"

    response = client.post("/api/download", json={"url": url, "format_id": "bestaudio"})
    assert response.status_code == 200
    queued = response.json()

    job = wait_for_download(queued["id"])

    jobs = client.get("/api/jobs").json()
    assert len(jobs) == 1
    job_data = jobs[0]

    for field in ("created_at", "updated_at"):
        ts = job_data[field]
        assert ts is not None, f"{field} is None"
        assert ts.endswith(("+00:00", "Z")), f"{field}={ts!r}"
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        assert parsed.tzinfo == timezone.utc


@pytest.mark.asyncio
async def test_files_modified_is_utc_from_mtime(client, backend, downloads_dir):
    """GET /api/files lists a file whose mtime was set with os.utime to 1700000000;
    its `modified` parses to exactly datetime.fromtimestamp(1700000000, tz=timezone.utc)."""
    # Create a test file and set its mtime to a known epoch
    test_file = downloads_dir / "test_timestamp.mp4"
    test_file.write_bytes(b"test content")
    os.utime(test_file, (1700000000, 1700000000))

    # List files
    response = client.get("/api/files")
    assert response.status_code == 200
    body = response.json()

    # Find our test file
    entry = next((e for e in body["entries"] if e["name"] == "test_timestamp.mp4"), None)
    assert entry is not None, "test file not found in listing"
    modified = entry["modified"]
    assert modified is not None, "modified is None"
    assert modified.endswith(("+00:00", "Z")), f"modified={modified!r}"

    parsed = datetime.fromisoformat(modified.replace("Z", "+00:00"))
    assert parsed.tzinfo == timezone.utc

    # Exact match to the timestamp we set
    expected = datetime.fromtimestamp(1700000000, tz=timezone.utc)
    assert parsed == expected, f"expected {expected.isoformat()}, got {parsed.isoformat()}"


@pytest.mark.asyncio
async def test_naive_utc_from_db_is_serialized_as_utc(client, backend, downloads_dir):
    """A naive datetime in the DB (as the models store) is serialized with UTC offset."""
    # We can't easily inject a naive datetime into the DB without going through
    # the app, but we can check that the JobResponse/HistoryEntry models
    # serialize a naive datetime correctly via the UtcDatetime type.
    from models.schemas import JobResponse, HistoryEntry, FileEntry

    naive = datetime(2026, 11, 5, 15, 24, 20, 675680)  # no tzinfo

    # JobResponse
    job_resp = JobResponse(
        id="test-id",
        url="https://example.com",
        status="finished",
        created_at=naive,
        updated_at=naive,
    )
    job_json = job_resp.model_dump(mode="json")
    for field in ("created_at", "updated_at"):
        assert job_json[field].endswith(("+00:00", "Z")), f"job {field}={job_json[field]!r}"
        parsed = datetime.fromisoformat(job_json[field].replace("Z", "+00:00"))
        assert parsed == naive.replace(tzinfo=timezone.utc)

    # HistoryEntry
    hist = HistoryEntry(
        id="test-id",
        finished_at=naive,
    )
    hist_json = hist.model_dump(mode="json")
    assert hist_json["finished_at"].endswith(("+00:00", "Z"))
    parsed = datetime.fromisoformat(hist_json["finished_at"].replace("Z", "+00:00"))
    assert parsed == naive.replace(tzinfo=timezone.utc)

    # FileEntry
    file_entry = FileEntry(
        name="test.mp4",
        path="test.mp4",
        is_dir=False,
        size=100,
        modified=naive,
    )
    file_json = file_entry.model_dump(mode="json")
    assert file_json["modified"].endswith(("+00:00", "Z"))
    parsed = datetime.fromisoformat(file_json["modified"].replace("Z", "+00:00"))
    assert parsed == naive.replace(tzinfo=timezone.utc)