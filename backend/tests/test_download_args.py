"""DownloadManager._build_args and the output-line regexes."""

import pytest

from models.database import SettingsModel
from services.download_manager import FILEPATH_RE, PROGRESS_RE, Job, manager

URL = "https://example.com/watch?v=abc"


def _settings(**kw):
    values = dict(
        download_folder="/dl",
        audio_format="mp3",
        concurrent_downloads=2,
        ytdlp_path="/opt/yt-dlp",
        ffmpeg_path="ffmpeg",
        cookies_content=None,
        cookies_file_path=None,
    )
    values.update(kw)
    return SettingsModel(**values)


def _args(fmt, **kw):
    return manager._build_args(Job(URL, fmt), _settings(**kw))


def _after(args, flag):
    return args[args.index(flag) + 1]


@pytest.mark.parametrize("fmt", [None, "bestvideo"])
def test_default_and_bestvideo_merge_best(fmt):
    args = _args(fmt)
    assert args[0] == "/opt/yt-dlp"
    assert _after(args, "-f") == "bestvideo*+bestaudio/best"
    assert "-x" not in args
    assert args[-1] == URL


def test_bestaudio_extracts_audio_in_configured_format():
    args = _args("bestaudio", audio_format="opus")
    assert _after(args, "-f") == "bestaudio/best"
    assert "-x" in args
    assert _after(args, "--audio-format") == "opus"
    assert args[-1] == URL


def test_custom_format_id_is_passed_through():
    args = _args("137+140")
    assert _after(args, "-f") == "137+140"
    assert "-x" not in args
    assert args[-1] == URL


def test_output_template_uses_download_folder():
    assert _after(_args(None), "-o") == "/dl/%(title)s.%(ext)s"


def test_ffmpeg_location_only_for_real_path():
    assert "--ffmpeg-location" not in _args(None)
    args = _args(None, ffmpeg_path="/usr/local/bin/ffmpeg")
    assert _after(args, "--ffmpeg-location") == "/usr/local/bin/ffmpeg"


def test_explicit_cookies_file_is_passed():
    args = _args(None, cookies_file_path="/cookies/c.txt")
    assert _after(args, "--cookies") == "/cookies/c.txt"
    assert args[-1] == URL


@pytest.mark.parametrize(
    "line,groups",
    [
        ("PROGRESS downloading 42.5% 1.20MiB/s 00:12", ("downloading", "42.5", "1.20MiB/s", "00:12")),
        ("PROGRESS finished 100.0% NA NA", ("finished", "100.0", "NA", "NA")),
        ("PROGRESS downloading   7% Unknown Unknown", ("downloading", "7", "Unknown", "Unknown")),
    ],
)
def test_progress_re_matches(line, groups):
    m = PROGRESS_RE.match(line)
    assert m is not None
    assert m.groups() == groups


@pytest.mark.parametrize(
    "line",
    [
        "[download] 42.5% of 10MiB",
        "PROGRESS downloading abc% 1 2",
        "PROGRESS downloading 10% only-three",
        "",
    ],
)
def test_progress_re_rejects(line):
    assert PROGRESS_RE.match(line) is None


def test_filepath_re():
    m = FILEPATH_RE.match("OUTPATH /downloads/My Video [x].mp4")
    assert m and m.group(1) == "/downloads/My Video [x].mp4"
    assert FILEPATH_RE.match("[download] Destination: /downloads/a.mp4") is None
    assert FILEPATH_RE.match("OUTPATH") is None
