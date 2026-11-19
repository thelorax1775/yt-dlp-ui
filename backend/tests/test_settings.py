"""GET/POST /api/settings."""

from tests.conftest import FAKE_YTDLP_VERSION

NETSCAPE = (
    "# Netscape HTTP Cookie File\n"
    ".example.com\tTRUE\t/\tFALSE\t0\tsid\tabc\n"
)


def test_defaults_on_fresh_database(client):
    # `client` already points ytdlp_path/download_folder at test values.
    data = client.get("/api/settings").json()
    assert data["audio_format"] == "mp3"
    assert data["concurrent_downloads"] == 2
    assert data["ffmpeg_path"] == "ffmpeg"
    assert data["cookies_configured"] is False


def test_round_trip(client, fake_ytdlp, tmp_path):
    folder = str(tmp_path / "elsewhere")
    resp = client.post(
        "/api/settings",
        json={"download_folder": folder, "audio_format": "opus", "concurrent_downloads": 3},
    )
    assert resp.status_code == 200
    got = client.get("/api/settings").json()
    assert got == resp.json()
    assert got["download_folder"] == folder
    assert got["audio_format"] == "opus"
    assert got["concurrent_downloads"] == 3
    # untouched fields keep their value
    assert got["ytdlp_path"] == fake_ytdlp
    assert got["ytdlp_version"] == FAKE_YTDLP_VERSION


def test_concurrent_downloads_out_of_range_is_422(client):
    assert client.post("/api/settings", json={"concurrent_downloads": 0}).status_code == 422
    assert client.post("/api/settings", json={"concurrent_downloads": 11}).status_code == 422


def test_cookies_must_be_netscape_format(client):
    resp = client.post("/api/settings", json={"cookies_content": "this is not cookies"})
    assert resp.status_code == 400
    assert "Netscape" in resp.json()["detail"]
    assert client.get("/api/settings").json()["cookies_configured"] is False


def test_cookies_saved_and_cleared(client):
    from services import cookies
    import os

    resp = client.post("/api/settings", json={"cookies_content": NETSCAPE})
    assert resp.status_code == 200
    assert resp.json()["cookies_configured"] is True
    # the content itself is write-only
    assert "cookies_content" not in resp.json()
    assert os.path.isfile(cookies.COOKIES_PATH)
    assert oct(os.stat(cookies.COOKIES_PATH).st_mode & 0o777) == "0o600"

    resp = client.post("/api/settings", json={"cookies_content": ""})
    assert resp.json()["cookies_configured"] is False
    assert not os.path.exists(cookies.COOKIES_PATH)
