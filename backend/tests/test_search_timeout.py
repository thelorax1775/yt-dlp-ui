"""Tests for search timeout behavior using the same limit as /api/info."""

import os
import time
import pytest


def test_search_times_out_and_kills_process(client, backend, monkeypatch, real_program, tmp_path):
    """Search with a too-long yt-dlp returns 400 and the process is reaped."""
    import services.metadata as metadata

    # Lower the timeout to 1 second for the test
    metadata.LOOKUP_TIMEOUT_SECONDS = 1

    # Create a fake yt-dlp that writes its PID and sleeps for 30 seconds
    fake_ytdlp = tmp_path / "yt-dlp-slow"
    pid_file = tmp_path / "pid.txt"
    fake_ytdlp.write_text(
        f"""#!/bin/sh
echo $$ > {pid_file}
sleep 30
echo '{{\"entries\":[]}}'
"""
    )
    fake_ytdlp.chmod(0o755)

    real_program(fake_ytdlp)
    r = client.post("/api/settings", json={"ytdlp_path": str(fake_ytdlp)})
    assert r.status_code == 200

    start = time.monotonic()
    response = client.get("/api/search", params={"q": "x"})
    elapsed = time.monotonic() - start

    assert response.status_code == 400
    assert "timed out" in response.json()["detail"].lower()
    assert elapsed < 5, f"search took {elapsed:.1f}s, should be under 5s with 1s timeout"

    # Give the reaper up to 2 seconds to finish
    time.sleep(2)

    # The PID file should exist and the process should no longer be running
    assert pid_file.exists()
    pid = int(pid_file.read_text().strip())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_search_works_with_fast_ytdlp(client, backend, real_program, tmp_path):
    """A fast yt-dlp that exits 0 with empty entries still gives 200 with results == []."""
    fake_ytdlp = tmp_path / "yt-dlp-fast"
    fake_ytdlp.write_text(
        """#!/bin/sh
echo '{"entries":[]}'
"""
    )
    fake_ytdlp.chmod(0o755)

    real_program(fake_ytdlp)
    r = client.post("/api/settings", json={"ytdlp_path": str(fake_ytdlp)})
    assert r.status_code == 200

    response = client.get("/api/search", params={"q": "x"})
    assert response.status_code == 200
    assert response.json()["results"] == []