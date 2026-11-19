"""Opening a database file written by an older version of the app.

``create_all`` never adds a column to a table that already exists, so every
settings column introduced after the first release has to be added by
``_migrate_settings_columns``. Each test writes a database with an old
``settings`` table by hand, then starts the app on it.
"""

import sqlite3

import pytest

# The settings table as the first release created it.
SCHEMA_V1 = """
CREATE TABLE settings (
    id INTEGER NOT NULL,
    download_folder TEXT NOT NULL,
    audio_format VARCHAR(16) NOT NULL,
    concurrent_downloads INTEGER NOT NULL,
    ytdlp_path TEXT NOT NULL,
    ffmpeg_path TEXT NOT NULL,
    PRIMARY KEY (id)
)
"""

# After cookie support, before the audio folder: what main created until now.
SCHEMA_BEFORE_AUDIO_FOLDER = """
CREATE TABLE settings (
    id INTEGER NOT NULL,
    download_folder TEXT NOT NULL,
    audio_format VARCHAR(16) NOT NULL,
    concurrent_downloads INTEGER NOT NULL,
    ytdlp_path TEXT NOT NULL,
    ffmpeg_path TEXT NOT NULL,
    cookies_content TEXT,
    cookies_file_path TEXT,
    PRIMARY KEY (id)
)
"""


def columns(db_path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {row[1] for row in conn.execute("PRAGMA table_info(settings)")}


@pytest.fixture
def old_database(backend):
    """Write an old-schema database where the app will look for its own."""

    def create(schema: str):
        assert not backend.db_path.exists()
        with sqlite3.connect(backend.db_path) as conn:
            conn.execute(schema)
            conn.execute(
                "INSERT INTO settings (id, download_folder, audio_format,"
                " concurrent_downloads, ytdlp_path, ffmpeg_path)"
                " VALUES (1, '/mnt/old-media', 'opus', 3, '/opt/yt-dlp', '/opt/ffmpeg')"
            )
        return backend.db_path

    return create


@pytest.mark.parametrize(
    "schema", [SCHEMA_BEFORE_AUDIO_FOLDER, SCHEMA_V1], ids=["before-audio-folder", "v1"]
)
def test_app_starts_on_an_old_database_and_reads_settings(old_database, request, schema):
    db_path = old_database(schema)
    assert "audio_download_folder" not in columns(db_path)

    client = request.getfixturevalue("client")  # starts the app on that file
    response = client.get("/api/settings")

    assert response.status_code == 200, response.text
    settings = response.json()
    # Nothing the user had configured is lost...
    assert settings["download_folder"] == "/mnt/old-media"
    assert settings["audio_format"] == "opus"
    assert settings["concurrent_downloads"] == 3
    assert settings["ytdlp_path"] == "/opt/yt-dlp"
    assert settings["ffmpeg_path"] == "/opt/ffmpeg"
    # ...and the new setting starts out unset.
    assert settings["audio_download_folder"] is None
    assert {"audio_download_folder", "cookies_content", "cookies_file_path"} <= columns(db_path)


def test_audio_folder_can_be_set_on_a_migrated_database(old_database, request, backend):
    old_database(SCHEMA_BEFORE_AUDIO_FOLDER)
    client = request.getfixturevalue("client")

    posted = client.post("/api/settings", json={"audio_download_folder": "/mnt/music"})

    assert posted.status_code == 200, posted.text
    assert client.get("/api/settings").json()["audio_download_folder"] == "/mnt/music"
    with sqlite3.connect(backend.db_path) as conn:
        assert conn.execute("SELECT audio_download_folder FROM settings").fetchall() == [
            ("/mnt/music",)
        ]


def test_old_database_downloads_still_go_to_the_download_folder(
    old_database, request, backend
):
    old_database(SCHEMA_BEFORE_AUDIO_FOLDER)
    client = request.getfixturevalue("client")
    wait_for_download = request.getfixturevalue("wait_for_download")
    folder = backend.tmp_path / "old-downloads"
    client.post("/api/settings", json={"download_folder": str(folder)})

    job = client.post(
        "/api/download",
        json={"url": "https://example.invalid/watch?v=song", "format_id": "bestaudio"},
    ).json()
    wait_for_download(job["id"])

    (argv,) = backend.subprocess.download_calls()
    assert argv[argv.index("-o") + 1] == str(folder / "%(title)s.%(ext)s")


def test_migration_is_safe_to_run_again(old_database, backend):
    """Every start runs the migration; the second run must change nothing."""
    import asyncio

    db_path = old_database(SCHEMA_BEFORE_AUDIO_FOLDER)

    async def start_twice():
        await backend.database.init_db()
        first = columns(db_path)
        await backend.database.init_db()
        await backend.database.engine.dispose()
        return first

    first = asyncio.run(start_twice())

    assert "audio_download_folder" in first
    assert columns(db_path) == first
