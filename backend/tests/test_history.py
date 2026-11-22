"""History API: deleting one entry or clearing the whole history.

The deletes only touch the ``history`` table: downloaded files and the jobs
list stay as they are.
"""

import pytest


def _listing(folder):
    return sorted(p.name for p in folder.iterdir())


def test_delete_one_history_entry(client, downloads_dir, wait_for_download):
    """DELETE /api/history/{id} removes that row and leaves the other one."""
    job1 = client.post("/api/download", json={"url": "https://example.invalid/v1"}).json()
    job1 = wait_for_download(job1["id"])
    job2 = client.post("/api/download", json={"url": "https://example.invalid/v2"}).json()
    job2 = wait_for_download(job2["id"])

    history = client.get("/api/history").json()
    assert len(history) == 2
    first_id, second_id = history[0]["id"], history[1]["id"]

    # A file on disk that the delete must not touch.
    keep = downloads_dir / "keep.mp4"
    keep.write_bytes(b"video")
    before = _listing(downloads_dir)

    response = client.delete(f"/api/history/{first_id}")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "id": first_id}

    history = client.get("/api/history").json()
    assert len(history) == 1
    assert history[0]["id"] == second_id

    # The file is still there and the jobs list is unchanged.
    assert keep.exists()
    assert _listing(downloads_dir) == before
    job_ids = {j["id"] for j in client.get("/api/jobs").json()}
    assert job1["id"] in job_ids
    assert job2["id"] in job_ids


def test_delete_unknown_history_entry(client, downloads_dir, wait_for_download):
    """DELETE /api/history/999999 answers 404 and changes nothing."""
    job = client.post("/api/download", json={"url": "https://example.invalid/v"}).json()
    wait_for_download(job["id"])

    response = client.delete("/api/history/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "History entry not found"}
    assert len(client.get("/api/history").json()) == 1


def test_clear_history(client, downloads_dir, wait_for_download):
    """DELETE /api/history removes every row and reports how many."""
    job1 = client.post("/api/download", json={"url": "https://example.invalid/v1"}).json()
    job1 = wait_for_download(job1["id"])
    job2 = client.post("/api/download", json={"url": "https://example.invalid/v2"}).json()
    job2 = wait_for_download(job2["id"])

    assert len(client.get("/api/history").json()) == 2

    # A file on disk that the clear must not touch.
    keep = downloads_dir / "keep.mp4"
    keep.write_bytes(b"video")
    before = _listing(downloads_dir)

    response = client.delete("/api/history")

    assert response.status_code == 200
    assert response.json() == {"status": "cleared", "count": 2}
    assert client.get("/api/history").json() == []

    # The file is still there and the jobs list is unchanged.
    assert keep.exists()
    assert _listing(downloads_dir) == before
    job_ids = {j["id"] for j in client.get("/api/jobs").json()}
    assert job1["id"] in job_ids
    assert job2["id"] in job_ids

    # Clearing an already empty history is a no-op.
    response = client.delete("/api/history")

    assert response.status_code == 200
    assert response.json() == {"status": "cleared", "count": 0}
    assert client.get("/api/history").json() == []
    assert keep.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
