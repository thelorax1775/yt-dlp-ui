"""GET /api/search over HTTP.

The argument building and parsing helpers are covered in test_search.py; this
checks the route is registered and how it answers. yt-dlp is never run; see
FakeSubprocess in conftest.py.
"""

FLAT_LISTING = {
    "entries": [
        {
            "id": "aaa111",
            "title": "Older video",
            "url": "https://www.youtube.com/watch?v=aaa111",
            "channel": "Some Channel",
            "channel_url": "https://www.youtube.com/@somechannel",
            "duration": 61,
            "upload_date": "20260102",
            "view_count": 10,
        },
        {
            "id": "bbb222",
            "title": "Newer video",
            "url": "https://www.youtube.com/watch?v=bbb222",
            "channel": "Some Channel",
            "channel_url": "https://www.youtube.com/@somechannel",
            "duration": 62,
            "upload_date": "20260304",
            "view_count": 20,
        },
    ]
}


def listing_calls(backend):
    return [c for c in backend.subprocess.calls if "--flat-playlist" in c]


def test_search_without_parameters_is_a_bad_request(client, backend):
    response = client.get("/api/search")

    assert response.status_code == 400
    assert response.json() == {"detail": "Provide either 'q' or 'channel'"}
    assert backend.subprocess.calls == []


def test_search_with_empty_query_is_a_bad_request(client, backend):
    assert client.get("/api/search", params={"q": ""}).status_code == 400
    assert backend.subprocess.calls == []


def test_search_rejects_a_channel_that_is_not_youtube(client, backend):
    response = client.get("/api/search", params={"channel": "https://example.invalid/@x"})

    assert response.status_code == 400
    assert "not a youtube channel URL" in response.json()["detail"]
    assert backend.subprocess.calls == []


def test_search_by_words_returns_results_in_yt_dlp_order(client, backend):
    backend.subprocess.metadata = FLAT_LISTING

    response = client.get("/api/search", params={"q": "cats", "limit": 2})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "search"
    assert body["query"] == "cats"
    assert [r["id"] for r in body["results"]] == ["aaa111", "bbb222"]
    assert body["results"][0] == {
        "id": "aaa111",
        "title": "Older video",
        "url": "https://www.youtube.com/watch?v=aaa111",
        "uploader": "Some Channel",
        "channel_url": "https://www.youtube.com/@somechannel",
        "duration": 61,
        "upload_date": "2026-01-02",
        "view_count": 10,
    }
    (listing,) = listing_calls(backend)
    assert listing[0] == "yt-dlp"
    assert listing[-1] == "ytsearch2:cats"


def test_search_by_channel_lists_newest_first(client, backend):
    backend.subprocess.metadata = FLAT_LISTING

    response = client.get("/api/search", params={"channel": "@somechannel"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "channel"
    assert body["channel"] == "https://www.youtube.com/@somechannel"
    assert [r["upload_date"] for r in body["results"]] == ["2026-03-04", "2026-01-02"]
    (listing,) = listing_calls(backend)
    assert listing[-1] == "https://www.youtube.com/@somechannel/videos"
    assert listing[listing.index("--playlist-end") + 1] == "5"


def test_search_limit_is_clamped_to_ten(client, backend):
    backend.subprocess.metadata = {"entries": []}

    response = client.get("/api/search", params={"q": "cats", "limit": 500})

    assert response.status_code == 200, response.text
    assert response.json()["results"] == []
    (listing,) = listing_calls(backend)
    assert listing[-1] == "ytsearch10:cats"


def test_search_reports_a_yt_dlp_failure_as_a_bad_request(client, monkeypatch):
    import asyncio

    class FailedProcess:
        returncode = 1

        async def communicate(self):
            return b"", b"WARNING: noise\nERROR: Unable to download API page\n"

    async def failing(*_args, **_kwargs):
        return FailedProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", failing)

    response = client.get("/api/search", params={"q": "cats"})

    assert response.status_code == 400
    assert response.json() == {"detail": "yt-dlp failed: ERROR: Unable to download API page"}
