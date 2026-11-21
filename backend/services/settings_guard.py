"""Checks for the settings that decide which files and programs the app touches.

The API has no login, so anyone who can reach it can post settings. These
checks keep two of them from being turned into a way out of the download
folder or into running an arbitrary program:

* ``download_folder`` / ``audio_download_folder`` become the root of the file
  manager and the place yt-dlp writes to. They must not be the filesystem
  root and must not overlap the app data directory (database, cookies.txt).
* ``ytdlp_path`` is executed as given, on save and on every download. It must
  be the bare name ``yt-dlp`` or an absolute path to an executable file whose
  name starts with ``yt-dlp``.

* ``ffmpeg_path`` is handed to yt-dlp as ``--ffmpeg-location`` and run. It must
  be the bare name ``ffmpeg``, an absolute path to an executable file whose
  name starts with ``ffmpeg``, or an absolute folder holding an executable
  ``ffmpeg`` (or ``ffmpeg.exe``).
* ``cookies_file_path`` is handed to yt-dlp as ``--cookies``, which reads it
  and rewrites it. It must be an existing regular file outside the app data
  directory whose content looks like a Netscape cookies file.

They narrow what a visitor can do; they are not a substitute for a login.
"""

import os
from pathlib import Path

from models.database import DATA_DIR
from services.cookies import validate_cookies_content

YTDLP_NAME = "yt-dlp"
FFMPEG_NAME = "ffmpeg"
_COOKIES_READ_LIMIT = 1024 * 1024


class SettingsError(ValueError):
    """A settings value was refused; the message is safe to show to the user."""


def validate_folder(value: str, label: str = "Download folder") -> str:
    """Return the folder to store (trimmed) or raise SettingsError."""
    folder = (value or "").strip()
    if not folder:
        raise SettingsError(f"{label} must not be empty")
    if not os.path.isabs(folder):
        raise SettingsError(f"{label} must be an absolute path")
    try:
        # Symlinks are followed, so a link to a forbidden folder is judged by
        # where it leads.
        resolved = Path(os.path.realpath(folder))
        data_dir = Path(os.path.realpath(DATA_DIR))
    except (OSError, ValueError):
        raise SettingsError(f"{label} is not a usable path")

    if resolved == Path(resolved.anchor):
        raise SettingsError(f"{label} must not be the filesystem root")
    if (
        resolved == data_dir
        or data_dir.is_relative_to(resolved)
        or resolved.is_relative_to(data_dir)
    ):
        raise SettingsError(
            f"{label} must not contain, equal or be inside the app data "
            "directory (it holds the database and cookies)"
        )

    # Must exist as a folder, or be creatable: the nearest existing parent is
    # a folder this process may create entries in. Nothing is created here.
    existing = resolved
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    if not existing.is_dir():
        raise SettingsError(f"{label} is not a folder")
    if existing != resolved and not os.access(existing, os.W_OK | os.X_OK):
        raise SettingsError(f"{label} does not exist and cannot be created")
    return folder


def validate_ytdlp_path(value: str) -> str:
    """Return the yt-dlp program to store (trimmed) or raise SettingsError."""
    path = (value or "").strip()
    if path == YTDLP_NAME:
        return path
    message = (
        f"yt-dlp path must be '{YTDLP_NAME}' or an absolute path to an "
        f"executable file whose name starts with '{YTDLP_NAME}'"
    )
    if "\x00" in path or not os.path.isabs(path):
        raise SettingsError(message)
    if not os.path.basename(path).startswith(YTDLP_NAME):
        raise SettingsError(message)
    if not os.path.isfile(path) or not os.access(path, os.X_OK):
        raise SettingsError(message)
    return path


def _is_executable_file(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def validate_ffmpeg_path(value: str) -> str:
    """Return the ffmpeg location to store (trimmed) or raise SettingsError."""
    path = (value or "").strip()
    if path == FFMPEG_NAME:
        return path
    message = (
        f"ffmpeg path must be '{FFMPEG_NAME}', an absolute path to an "
        f"executable file whose name starts with '{FFMPEG_NAME}', or an "
        f"absolute path to a folder containing an executable '{FFMPEG_NAME}'"
    )
    if "\x00" in path or not os.path.isabs(path):
        raise SettingsError(message)
    if os.path.isdir(path):
        if any(
            _is_executable_file(os.path.join(path, name))
            for name in (FFMPEG_NAME, FFMPEG_NAME + ".exe")
        ):
            return path
        raise SettingsError(message)
    if os.path.basename(path).startswith(FFMPEG_NAME) and _is_executable_file(path):
        return path
    raise SettingsError(message)


def validate_cookies_file_path(value: str) -> str:
    """Return the cookies file to store (trimmed) or raise SettingsError."""
    path = (value or "").strip()
    message = (
        "Cookies file must be an absolute path to an existing cookies.txt "
        "file (Netscape format) outside the app data directory"
    )
    if "\x00" in path or not os.path.isabs(path):
        raise SettingsError(message)
    try:
        resolved = Path(os.path.realpath(path))
        data_dir = Path(os.path.realpath(DATA_DIR))
    except (OSError, ValueError):
        raise SettingsError(message)
    if resolved == data_dir or resolved.is_relative_to(data_dir):
        raise SettingsError(
            "Cookies file must not be inside the app data directory; paste "
            "cookies into the cookies box instead"
        )
    if not resolved.is_file():
        raise SettingsError(message)
    try:
        with open(resolved, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(_COOKIES_READ_LIMIT)
    except OSError:
        raise SettingsError("Cookies file cannot be read")
    if not validate_cookies_content(content):
        raise SettingsError("Cookies file is not in Netscape cookies.txt format")
    return path
