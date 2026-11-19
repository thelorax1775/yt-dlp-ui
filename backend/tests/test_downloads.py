"""Download manager: progress parsing, yt-dlp argument building, job flow.

yt-dlp is never run; see FakeSubprocess in conftest.py.
"""

import os
from types import SimpleNamespace

import pytest


def make_settings(**overrides):
    values = dict(
        download_folder="/downloads",
        audio_download_folder=None,
        audio_format="mp3",
        ytdlp_path="yt-dlp",
        ffmpeg_path="ffmpeg",
        cookies_file_path=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def option_value(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1]


# ---- progress lines ----


@pytest.mark.parametrize(
    "line, expected",
    [
        ("PROGRESS downloading  42.3% 1.20MiB/s 00:12", ("downloading", "42.3", "1.20MiB/s", "00:12")),
        ("PROGRESS downloading   0.0% 512.00KiB/s 01:02:03", ("downloading", "0.0", "512.00KiB/s", "01:02:03")),
        ("PROGRESS downloading 100.0% 3.4MiB/s 00:00", ("downloading", "100.0", "3.4MiB/s", "00:00")),
        ("PROGRESS finished 100.0% 2.00MiB/s NA", ("finished", "100.0", "2.00MiB/s", "NA")),
    ],
)
def test_progress_line_is_parsed(backend, line, expected):
    match = backend.download_manager.PROGRESS_RE.match(line)

    assert match is not None
    assert match.groups() == expected


@pytest.mark.parametrize(
    "line",
    [
        "[download] Destination: /downloads/clip.mp4",
        "OUTPATH /downloads/clip.mp4",
        "ERROR: [generic] Unable to download webpage",
        "note: PROGRESS downloading 10.0% 1MiB/s 00:10",
        "",
    ],
)
def test_other_output_is_not_mistaken_for_progress(backend, line):
    assert backend.download_manager.PROGRESS_RE.match(line) is None


def test_final_path_line_is_parsed(backend):
    match = backend.download_manager.FILEPATH_RE.match("OUTPATH /downloads/My Clip [x].mp4")

    assert match is not None
    assert match.group(1) == "/downloads/My Clip [x].mp4"


# ---- yt-dlp argument list ----


def build_args(backend, format_id, **settings):
    dm = backend.download_manager
    job = dm.Job(url="https://example.invalid/watch?v=abc", format_id=format_id)
    return dm.manager._build_args(job, make_settings(**settings))


def test_build_args_default_format(backend):
    args = build_args(backend, None)

    assert args[0] == "yt-dlp"
    assert args[-1] == "https://example.invalid/watch?v=abc"
    assert "--no-playlist" in args
    assert option_value(args, "-f") == "bestvideo*+bestaudio/best"
    assert option_value(args, "--progress-template") == backend.download_manager.PROGRESS_TEMPLATE
    assert os.path.dirname(option_value(args, "-o")) == "/downloads"
    assert "-x" not in args
    assert "--cookies" not in args
    assert "--ffmpeg-location" not in args


def test_build_args_bestvideo_is_the_default_format(backend):
    assert option_value(build_args(backend, "bestvideo"), "-f") == "bestvideo*+bestaudio/best"


def test_build_args_audio(backend):
    args = build_args(backend, "bestaudio", audio_format="opus")

    assert option_value(args, "-f") == "bestaudio/best"
    assert "-x" in args
    assert option_value(args, "--audio-format") == "opus"


def test_build_args_explicit_format(backend):
    args = build_args(backend, "bestvideo[height<=720]+bestaudio/best")

    assert option_value(args, "-f") == "bestvideo[height<=720]+bestaudio/best"
    assert args.count("-f") == 1


def test_build_args_uses_configured_folder_binary_and_ffmpeg(backend):
    args = build_args(
        backend,
        None,
        download_folder="/mnt/media",
        ytdlp_path="/opt/bin/yt-dlp",
        ffmpeg_path="/opt/ffmpeg/bin",
    )

    assert args[0] == "/opt/bin/yt-dlp"
    assert os.path.dirname(option_value(args, "-o")) == "/mnt/media"
    assert option_value(args, "--ffmpeg-location") == "/opt/ffmpeg/bin"


def test_build_args_passes_explicit_cookies_file(backend):
    args = build_args(backend, None, cookies_file_path="/secrets/cookies.txt")

    assert option_value(args, "--cookies") == "/secrets/cookies.txt"


def test_build_args_uses_managed_cookies_file_when_present(backend):
    managed = backend.data_dir / "cookies.txt"
    managed.write_text("# Netscape HTTP Cookie File\n")

    args = build_args(backend, None)

    assert option_value(args, "--cookies") == str(managed)


# ---- API ----


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.invalid/x", "--exec=id", ""])
def test_download_rejects_urls_that_are_not_http(client, backend, url):
    response = client.post("/api/download", json={"url": url})

    assert response.status_code == 422
    assert client.get("/api/jobs").json() == []
    assert backend.subprocess.calls == []


def test_cancel_and_retry_of_unknown_job(client):
    assert client.delete("/api/jobs/no-such-job").status_code == 404
    assert client.post("/api/jobs/no-such-job/retry").status_code == 400


def test_successful_download_is_tracked_and_recorded_in_history(
    client, backend, downloads_dir, wait_for_job
):
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
    assert queued["url"] == url
    assert queued["format_id"] == "bestaudio"

    job = wait_for_job(queued["id"])
    assert job["status"] == "finished"
    assert job["progress"] == 100.0
    assert job["title"] == "Fake Title"
    assert job["file_path"] == final_path
    assert job["error"] is None

    # Exactly one download command, for this URL, into the configured folder.
    (argv,) = backend.subprocess.download_calls()
    assert argv[0] == "yt-dlp"
    assert argv[-1] == url
    assert os.path.dirname(option_value(argv, "-o")) == str(downloads_dir)
    assert option_value(argv, "-f") == "bestaudio/best"

    history = client.get("/api/history").json()
    assert [(h["id"], h["url"], h["title"], h["file_path"]) for h in history] == [
        (queued["id"], url, "Fake Title", final_path)
    ]


def test_failed_download_reports_the_error_and_is_not_in_history(
    client, backend, downloads_dir, wait_for_job
):
    backend.subprocess.download_returncode = 1
    backend.subprocess.download_lines = [
        "[generic] Extracting URL: https://example.invalid/gone",
        "ERROR: [generic] Unable to download webpage: HTTP Error 404: Not Found",
    ]

    queued = client.post("/api/download", json={"url": "https://example.invalid/gone"}).json()
    job = wait_for_job(queued["id"])

    assert job["status"] == "failed"
    assert job["error"] == "ERROR: [generic] Unable to download webpage: HTTP Error 404: Not Found"
    assert client.get("/api/history").json() == []
