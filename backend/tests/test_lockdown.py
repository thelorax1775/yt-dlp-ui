"""Settings and cross-site access: what a visitor without a login cannot do.

The API has no login, so these checks are what keeps a posted setting (or a
website open in the user's browser) from reaching the database and cookies or
from starting an arbitrary program.
"""

import os

import pytest

EVIL = "https://evil.example"
OK = "https://ok.example"


def preflight(client, origin, path="/api/settings", method="POST"):
    return client.options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type",
        },
    )


def stored(db, column):
    return db(f"SELECT {column} FROM settings WHERE id = 1")[0][0]


# ---- cross-site access (CORS) ----


def test_no_website_is_allowed_by_default(client):
    response = preflight(client, EVIL)

    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-methods" not in response.headers


@pytest.mark.parametrize("path", ["/api/health", "/api/settings", "/api/files"])
def test_plain_requests_from_another_site_get_no_cors_header_by_default(client, path):
    response = client.get(path, headers={"Origin": EVIL})

    assert "access-control-allow-origin" not in response.headers


@pytest.mark.cors_origins(OK)
def test_listed_origin_is_allowed_and_others_are_not(client):
    allowed = preflight(client, OK)
    refused = preflight(client, EVIL)

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == OK
    assert "POST" in allowed.headers["access-control-allow-methods"]
    assert "access-control-allow-origin" not in refused.headers

    assert client.get("/api/health", headers={"Origin": OK}).headers[
        "access-control-allow-origin"
    ] == OK
    assert "access-control-allow-origin" not in client.get(
        "/api/health", headers={"Origin": EVIL}
    ).headers


@pytest.mark.cors_origins(f" {OK}/ , https://second.example ,, ")
def test_origin_list_is_comma_separated_and_tolerates_spaces_and_slashes(client):
    assert preflight(client, OK).headers["access-control-allow-origin"] == OK
    assert (
        preflight(client, "https://second.example").headers["access-control-allow-origin"]
        == "https://second.example"
    )
    assert "access-control-allow-origin" not in preflight(client, EVIL).headers


@pytest.mark.cors_origins("*")
def test_wildcard_origin_is_ignored(client):
    assert "access-control-allow-origin" not in preflight(client, EVIL).headers
    assert "access-control-allow-origin" not in client.get(
        "/api/health", headers={"Origin": EVIL}
    ).headers


@pytest.mark.parametrize(
    "content_type", ["text/plain", "application/x-www-form-urlencoded", None]
)
def test_post_a_website_can_send_unasked_cannot_change_settings(client, db, content_type):
    # Browsers send these without a preflight, so the missing CORS headers do
    # not stop them. The API must not read such a body as JSON.
    request = client.build_request(
        "POST", "/api/settings", content=b'{"audio_format": "flac"}', headers={"Origin": EVIL}
    )
    request.headers.pop("content-type", None)
    if content_type:
        request.headers["content-type"] = content_type

    response = client.send(request)

    assert response.status_code == 422
    assert stored(db, "audio_format") == "mp3"


# ---- download folders ----


@pytest.fixture
def bad_folders(backend):
    inside = backend.data_dir / "sub"
    link = backend.tmp_path / "link-to-data"
    link.symlink_to(backend.data_dir)
    a_file = backend.tmp_path / "a-file"
    a_file.write_text("x")
    return {
        "filesystem root": "/",
        "root written another way": "//",
        "root through dot-dot": str(backend.tmp_path) + "/.." * 20,
        "app data directory": str(backend.data_dir),
        "app data directory with slash": str(backend.data_dir) + "/",
        "parent of the app data directory": str(backend.data_dir.parent),
        "folder inside the app data directory": str(inside),
        "link to the app data directory": str(link),
        "relative path": "relative/downloads",
        "dot": ".",
        "empty": "",
        "blank": "   ",
        "a file": str(a_file),
        "below a file": str(a_file / "sub"),
    }


BAD_FOLDER_CASES = [
    "filesystem root",
    "root written another way",
    "root through dot-dot",
    "app data directory",
    "app data directory with slash",
    "parent of the app data directory",
    "folder inside the app data directory",
    "link to the app data directory",
    "relative path",
    "dot",
    "empty",
    "blank",
    "a file",
    "below a file",
]


@pytest.mark.parametrize("case", BAD_FOLDER_CASES)
def test_download_folder_refuses_dangerous_values(client, db, bad_folders, case):
    response = client.post("/api/settings", json={"download_folder": bad_folders[case]})

    assert response.status_code == 422, response.text
    assert stored(db, "download_folder") == "/downloads"
    assert client.get("/api/settings").json()["download_folder"] == "/downloads"


@pytest.mark.parametrize(
    "case", [c for c in BAD_FOLDER_CASES if c not in ("empty", "blank")]
)
def test_audio_download_folder_refuses_dangerous_values(client, db, bad_folders, case):
    response = client.post("/api/settings", json={"audio_download_folder": bad_folders[case]})

    assert response.status_code == 422, response.text
    assert stored(db, "audio_download_folder") is None


def test_download_folder_accepts_an_existing_temp_folder(client, backend, db):
    folder = backend.tmp_path / "media"
    folder.mkdir()

    response = client.post("/api/settings", json={"download_folder": str(folder)})

    assert response.status_code == 200, response.text
    assert stored(db, "download_folder") == str(folder)


def test_download_folder_accepts_a_folder_that_can_be_created(client, backend, db):
    folder = backend.tmp_path / "new" / "deeper"

    response = client.post("/api/settings", json={"download_folder": f"  {folder} "})

    assert response.status_code == 200, response.text
    assert stored(db, "download_folder") == str(folder)
    # Checking is not creating.
    assert not (backend.tmp_path / "new").exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root may write anywhere")
def test_download_folder_refuses_a_folder_that_cannot_be_created(client, backend, db):
    locked = backend.tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o555)
    try:
        response = client.post("/api/settings", json={"download_folder": str(locked / "new")})
    finally:
        locked.chmod(0o755)

    assert response.status_code == 422
    assert stored(db, "download_folder") == "/downloads"


def test_refused_folder_stores_nothing_else_from_the_same_request(client, backend, db):
    cookies = "# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tFALSE\t0\tname\tvalue\n"

    response = client.post(
        "/api/settings",
        json={"download_folder": "/", "audio_format": "flac", "cookies_content": cookies},
    )

    assert response.status_code == 422
    assert stored(db, "audio_format") == "mp3"
    assert stored(db, "cookies_content") is None
    assert not os.path.exists(backend.cookies.COOKIES_PATH)


def test_database_cannot_be_fetched_by_moving_the_download_folder(client, backend):
    # The attack from the audit: point the root at the parent, then download.
    client.post("/api/settings", json={"download_folder": str(backend.data_dir.parent)})

    response = client.get("/api/files/download", params={"path": "data/test.db"})

    assert response.status_code != 200
    assert not response.content.startswith(b"SQLite format 3")


def test_unchanged_values_from_an_older_setup_do_not_block_other_settings(client, db):
    # The settings page posts every field. Values stored before these checks
    # existed must not make the whole form unsaveable.
    client.get("/api/settings")
    db("UPDATE settings SET download_folder = '/', ytdlp_path = '/opt/old/ytdl'")

    response = client.post(
        "/api/settings",
        json={"download_folder": "/", "ytdlp_path": "/opt/old/ytdl", "audio_format": "flac"},
    )

    assert response.status_code == 200, response.text
    assert stored(db, "audio_format") == "flac"
    assert stored(db, "download_folder") == "/"


# ---- yt-dlp program ----


@pytest.fixture
def script(backend, real_program):
    """An executable script that leaves a marker file when it is run."""
    marker = backend.tmp_path / "marker"

    def make(name: str, mode: int = 0o755):
        path = backend.tmp_path / "bin" / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(f"#!/bin/sh\necho ran > '{marker}'\necho 1.2.3\n")
        path.chmod(mode)
        real_program(path)
        return path

    make.marker = marker
    return make


def test_ytdlp_path_refuses_a_script_with_another_name_and_never_runs_it(
    client, backend, db, script
):
    path = script("x.sh")

    response = client.post("/api/settings", json={"ytdlp_path": str(path)})
    client.get("/api/settings")

    assert response.status_code == 422, response.text
    assert not script.marker.exists()
    assert backend.subprocess.calls_to(str(path)) == []
    assert stored(db, "ytdlp_path") == "yt-dlp"


@pytest.mark.parametrize(
    "value",
    [
        "sh -c id",
        "../../bin/sh",
        "/bin/sh",
        "sh",
        "bin/yt-dlp",
        "./yt-dlp",
        "yt-dlp --exec id",
        "yt-dlp\x00",
        "",
        "/nonexistent/yt-dlp",
    ],
)
def test_ytdlp_path_refuses_everything_but_ytdlp(client, backend, db, value):
    response = client.post("/api/settings", json={"ytdlp_path": value})
    client.get("/api/settings")

    assert response.status_code == 422, response.text
    assert stored(db, "ytdlp_path") == "yt-dlp"
    # Only the stored default was ever asked for its version.
    assert all(call[0] == "yt-dlp" for call in backend.subprocess.calls)


def test_ytdlp_path_refuses_a_file_that_is_not_executable(client, db, script):
    path = script("yt-dlp", mode=0o644)

    response = client.post("/api/settings", json={"ytdlp_path": str(path)})

    assert response.status_code == 422
    assert stored(db, "ytdlp_path") == "yt-dlp"
    assert not script.marker.exists()


def test_ytdlp_path_refuses_a_folder_named_like_ytdlp(client, backend, db):
    folder = backend.tmp_path / "yt-dlp"
    folder.mkdir()

    response = client.post("/api/settings", json={"ytdlp_path": str(folder)})

    assert response.status_code == 422
    assert stored(db, "ytdlp_path") == "yt-dlp"


def test_ytdlp_path_accepts_the_bare_name(client, db):
    response = client.post("/api/settings", json={"ytdlp_path": " yt-dlp "})

    assert response.status_code == 200, response.text
    assert stored(db, "ytdlp_path") == "yt-dlp"


@pytest.mark.parametrize("name", ["yt-dlp", "yt-dlp_linux"])
def test_ytdlp_path_accepts_an_absolute_path_to_an_executable_ytdlp(client, db, script, name):
    path = script(name)

    response = client.post("/api/settings", json={"ytdlp_path": str(path)})

    assert response.status_code == 200, response.text
    assert stored(db, "ytdlp_path") == str(path)
    assert response.json()["ytdlp_version"] == "1.2.3"


# ---- ffmpeg_path and cookies_file_path ----


def _exe(path, mode=0o755):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(mode)
    return path


def _current(client, field):
    return client.get("/api/settings").json()[field]


@pytest.mark.parametrize("value", ["/bin/sh", "relative/ffmpeg", "ffmpeg2", "/nonexistent/ffmpeg", "/tmp", ""])
def test_ffmpeg_path_refuses_other_programs(client, backend, db, value):
    before = _current(client, "ffmpeg_path")
    response = client.post("/api/settings", json={"ffmpeg_path": value})
    assert response.status_code == 422, response.text
    assert _current(client, "ffmpeg_path") == before


def test_ffmpeg_path_refuses_executable_with_another_name(client, backend):
    path = _exe(backend.tmp_path / "bin" / "notffmpeg")
    assert client.post("/api/settings", json={"ffmpeg_path": str(path)}).status_code == 422


def test_ffmpeg_path_refuses_non_executable_file_and_empty_folder(client, backend):
    plain = _exe(backend.tmp_path / "bin" / "ffmpeg", mode=0o644)
    assert client.post("/api/settings", json={"ffmpeg_path": str(plain)}).status_code == 422
    empty = backend.tmp_path / "empty"
    empty.mkdir()
    assert client.post("/api/settings", json={"ffmpeg_path": str(empty)}).status_code == 422


def test_ffmpeg_path_accepts_bare_name_file_and_folder(client, backend):
    assert client.post("/api/settings", json={"ffmpeg_path": "ffmpeg"}).status_code == 200
    path = _exe(backend.tmp_path / "bin" / "ffmpeg-6")
    response = client.post("/api/settings", json={"ffmpeg_path": str(path)})
    assert response.status_code == 200, response.text
    assert _current(client, "ffmpeg_path") == str(path)
    folder = backend.tmp_path / "ffdir"
    _exe(folder / "ffmpeg")
    assert client.post("/api/settings", json={"ffmpeg_path": str(folder)}).status_code == 200
    folder2 = backend.tmp_path / "ffdir2"
    _exe(folder2 / "ffmpeg.exe")
    assert client.post("/api/settings", json={"ffmpeg_path": str(folder2)}).status_code == 200


def test_cookies_file_path_refuses_bad_values(client, backend):
    inside = backend.db_path
    for value in ["/etc/passwd", str(backend.tmp_path / "nope.txt"), "cookies.txt", str(inside), str(backend.tmp_path)]:
        response = client.post("/api/settings", json={"cookies_file_path": value})
        assert response.status_code == 422, (value, response.text)
    assert _current(client, "cookies_file_path") is None


def test_cookies_file_path_refuses_link_into_data_dir(client, backend):
    link = backend.tmp_path / "link.txt"
    link.symlink_to(backend.db_path)
    assert client.post("/api/settings", json={"cookies_file_path": str(link)}).status_code == 422


def test_cookies_file_path_accepts_a_cookies_file_and_empty_clears(client, backend):
    f = backend.tmp_path / "c.txt"
    f.write_text("# Netscape HTTP Cookie File\n")
    response = client.post("/api/settings", json={"cookies_file_path": str(f)})
    assert response.status_code == 200, response.text
    assert _current(client, "cookies_file_path") == str(f)
    response = client.post("/api/settings", json={"cookies_file_path": ""})
    assert response.status_code == 200
    assert _current(client, "cookies_file_path") is None


def test_refused_ffmpeg_stores_nothing_else_from_the_request(client, backend):
    before = _current(client, "download_folder")
    folder = backend.tmp_path / "newdl"
    folder.mkdir()
    response = client.post(
        "/api/settings", json={"download_folder": str(folder), "ffmpeg_path": "/bin/sh"}
    )
    assert response.status_code == 422
    assert _current(client, "download_folder") == before


def test_unchanged_ffmpeg_and_cookies_values_are_not_rechecked(client, db):
    client.get("/api/settings")
    db("UPDATE settings SET ffmpeg_path = '/bin/sh', cookies_file_path = '/etc/passwd'")
    response = client.post(
        "/api/settings",
        json={"ffmpeg_path": "/bin/sh", "cookies_file_path": "/etc/passwd", "audio_format": "flac"},
    )
    assert response.status_code == 200, response.text
    assert stored(db, "ffmpeg_path") == "/bin/sh"
