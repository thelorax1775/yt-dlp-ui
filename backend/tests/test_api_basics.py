"""Health, settings and history endpoints."""

import os
import stat

NETSCAPE_COOKIES = (
    "# Netscape HTTP Cookie File\n"
    ".example.invalid\tTRUE\t/\tTRUE\t2147483647\tSID\tnot-a-real-cookie\n"
)


def test_health(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_startup_creates_database_in_temp_dir(client, backend):
    assert backend.db_path.is_file()
    assert backend.database.DATA_DIR == str(backend.data_dir)


# ---- settings ----


def test_settings_defaults(client, backend):
    response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json() == {
        "download_folder": "/downloads",
        "audio_format": "mp3",
        "concurrent_downloads": 2,
        "ytdlp_path": "yt-dlp",
        "ffmpeg_path": "ffmpeg",
        "cookies_configured": False,
        "cookies_file_path": None,
        "ytdlp_version": backend.subprocess.version,
    }
    # The version came from the fake, not from a real yt-dlp.
    assert backend.subprocess.calls == [["yt-dlp", "--version"]]


def test_settings_round_trip(client, backend):
    folder = str(backend.tmp_path / "media")

    posted = client.post(
        "/api/settings",
        json={"download_folder": folder, "audio_format": "opus", "concurrent_downloads": 4},
    )
    fetched = client.get("/api/settings")

    assert posted.status_code == 200
    assert fetched.json() == posted.json()
    assert fetched.json()["download_folder"] == folder
    assert fetched.json()["audio_format"] == "opus"
    assert fetched.json()["concurrent_downloads"] == 4
    # Fields that were not sent keep their values.
    assert fetched.json()["ytdlp_path"] == "yt-dlp"
    assert fetched.json()["ffmpeg_path"] == "ffmpeg"


def test_settings_partial_update_keeps_other_fields(client):
    client.post("/api/settings", json={"audio_format": "flac"})
    client.post("/api/settings", json={"concurrent_downloads": 3})

    body = client.get("/api/settings").json()
    assert body["audio_format"] == "flac"
    assert body["concurrent_downloads"] == 3


def test_settings_rejects_out_of_range_concurrency(client):
    for value in (0, 11, -1):
        response = client.post("/api/settings", json={"concurrent_downloads": value})
        assert response.status_code == 422, value

    assert client.get("/api/settings").json()["concurrent_downloads"] == 2


def test_settings_rejects_cookies_that_are_not_netscape_format(client, backend):
    response = client.post("/api/settings", json={"cookies_content": "just some text"})

    assert response.status_code == 400
    assert client.get("/api/settings").json()["cookies_configured"] is False
    assert not (backend.data_dir / "cookies.txt").exists()


def test_settings_stores_cookies_privately_and_never_returns_them(client, backend):
    response = client.post("/api/settings", json={"cookies_content": NETSCAPE_COOKIES})

    assert response.status_code == 200
    assert response.json()["cookies_configured"] is True
    assert "not-a-real-cookie" not in response.text
    assert "not-a-real-cookie" not in client.get("/api/settings").text

    cookies_file = backend.data_dir / "cookies.txt"
    assert cookies_file.read_text() == NETSCAPE_COOKIES.strip()
    assert stat.S_IMODE(os.stat(cookies_file).st_mode) == 0o600


def test_settings_empty_cookies_clears_them(client, backend):
    client.post("/api/settings", json={"cookies_content": NETSCAPE_COOKIES})

    response = client.post("/api/settings", json={"cookies_content": ""})

    assert response.status_code == 200
    assert response.json()["cookies_configured"] is False
    assert not (backend.data_dir / "cookies.txt").exists()


# ---- history ----


def test_history_is_empty_on_a_fresh_database(client):
    response = client.get("/api/history")

    assert response.status_code == 200
    assert response.json() == []


def test_history_lists_newest_first(client, db):
    rows = [
        ("id-old", "https://example.invalid/old", "Old", "2026-01-01 10:00:00.000000"),
        ("id-new", "https://example.invalid/new", "New", "2026-03-01 10:00:00.000000"),
        ("id-mid", "https://example.invalid/mid", "Mid", "2026-02-01 10:00:00.000000"),
    ]
    for row in rows:
        db(
            "INSERT INTO history (id, url, title, file_path, format_id, finished_at) "
            "VALUES (?, ?, ?, '/downloads/x.mp4', 'bestvideo', ?)",
            row,
        )

    response = client.get("/api/history")

    assert response.status_code == 200
    body = response.json()
    assert [entry["id"] for entry in body] == ["id-new", "id-mid", "id-old"]
    assert body[0] == {
        "id": "id-new",
        "url": "https://example.invalid/new",
        "title": "New",
        "thumbnail": None,
        "file_path": "/downloads/x.mp4",
        "format_id": "bestvideo",
        "finished_at": "2026-03-01T10:00:00",
    }
