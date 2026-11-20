"""Tests for fractional number handling in /api/info and /api/search.

yt-dlp can return fractional durations, filesizes and view counts for non-YouTube
sites. Pydantic's Optional[int] rejects these with a fractional part. The fix
adds a WholeNumber type that coerces float -> int (truncating) before validation.
"""

import pytest


class TestFractionalNumbersInInfo:
    """GET /api/info with fractional metadata."""

    def test_info_fractional_duration_and_filesize(self, client, backend):
        """duration and filesize_approx with fractional parts are truncated to ints."""
        backend.subprocess.metadata = {
            "title": "t",
            "duration": 212.5,
            "formats": [
                {
                    "format_id": "1",
                    "ext": "mp4",
                    "height": 720,
                    "vcodec": "avc1",
                    "filesize_approx": 1234.5,
                }
            ],
        }

        response = client.get("/api/info", params={"url": "https://x.invalid/v"})
        assert response.status_code == 200, response.text

        body = response.json()
        # Duration should be truncated to 212
        assert body["duration"] == 212
        # Format's filesize should be truncated to 1234
        assert body["formats"][0]["filesize"] == 1234
        # Resolution option's filesize should also be truncated to 1234
        assert body["resolutions"][0]["filesize"] == 1234

    def test_info_whole_number_still_works(self, client, backend):
        """Integer inputs still produce the same integer outputs."""
        backend.subprocess.metadata = {
            "title": "t",
            "duration": 212,
            "formats": [
                {
                    "format_id": "1",
                    "ext": "mp4",
                    "height": 720,
                    "vcodec": "avc1",
                    "filesize_approx": 1234,
                }
            ],
        }

        response = client.get("/api/info", params={"url": "https://x.invalid/v"})
        assert response.status_code == 200, response.text

        body = response.json()
        assert body["duration"] == 212
        assert body["formats"][0]["filesize"] == 1234
        assert body["resolutions"][0]["filesize"] == 1234


class TestFractionalNumbersInSearch:
    """GET /api/search with fractional metadata."""

    def test_search_fractional_duration_and_view_count(self, client, backend, monkeypatch):
        """duration and view_count with fractional parts are truncated to ints."""
        from services import search as s

        async def fake_run_ytdlp_json(args):
            if any(str(a).startswith("ytsearch") for a in args):
                return {
                    "entries": [
                        {
                            "id": "abc",
                            "title": "x",
                            "duration": 10.5,
                            "view_count": 3.0,
                        }
                    ]
                }
            # Per-video enrichment lookup
            return {"title": "x", "duration": 10.5}

        monkeypatch.setattr(s, "run_ytdlp_json", fake_run_ytdlp_json)

        response = client.get("/api/search", params={"q": "x"})
        assert response.status_code == 200, response.text

        body = response.json()
        assert body["results"][0]["duration"] == 10
        assert body["results"][0]["view_count"] == 3

    def test_search_whole_number_still_works(self, client, backend, monkeypatch):
        """Integer inputs still produce the same integer outputs."""
        from services import search as s

        async def fake_run_ytdlp_json(args):
            if any(str(a).startswith("ytsearch") for a in args):
                return {
                    "entries": [
                        {
                            "id": "abc",
                            "title": "x",
                            "duration": 10,
                            "view_count": 3,
                        }
                    ]
                }
            return {"title": "x", "duration": 10}

        monkeypatch.setattr(s, "run_ytdlp_json", fake_run_ytdlp_json)

        response = client.get("/api/search", params={"q": "x"})
        assert response.status_code == 200, response.text

        body = response.json()
        assert body["results"][0]["duration"] == 10
        assert body["results"][0]["view_count"] == 3