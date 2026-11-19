"""Checks for network-share input, run before anything reaches `mount`.

The API has no login, so every field of a share is untrusted: it ends up in
the argument list of `mount`, in a credentials file, and in the path handed to
`umount`. Bad values are rejected, never escaped.

* ``remote``: NFS ``host:/path`` or SMB ``//host/share``; may not start with
  ``-`` (it would be read as an option), no whitespace or control characters.
* ``mount_point``: absolute, normalised (no ``..``), strictly inside the mounts
  base directory (env ``SHARES_BASE``, default ``/mnt``), and never equal to or
  inside the app data directory or a download folder.
* ``username`` / ``password`` / ``domain``: no newline, comma or NUL.
* ``options``: comma separated, only the keys in ``ALLOWED_OPTIONS``.
"""

import os
import re
from pathlib import Path
from typing import Optional

from models.database import DATA_DIR

DEFAULT_SHARES_BASE = "/mnt"

# key -> True when it needs a value (key=value), False for a bare flag.
ALLOWED_OPTIONS = {
    "ro": False,
    "rw": False,
    "soft": False,
    "hard": False,
    "noserverino": False,
    "vers": True,
    "nfsvers": True,
    "timeo": True,
    "retrans": True,
    "iocharset": True,
    "file_mode": True,
    "dir_mode": True,
    "uid": True,
    "gid": True,
}

_HOST = r"(?:[A-Za-z0-9][A-Za-z0-9._-]*|\[[0-9A-Fa-f:.]+\])"
_NFS_RE = re.compile(rf"^{_HOST}:/\S*$")
_SMB_RE = re.compile(rf"^//{_HOST}/[^/\s]\S*$")
_VALUE_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class ShareError(ValueError):
    """A share value was refused; the message is safe to show to the user."""


def shares_base() -> str:
    base = os.environ.get("SHARES_BASE", "").strip() or DEFAULT_SHARES_BASE
    return os.path.normpath(base)


def _bad_char(value: str, allow_space: bool = False) -> bool:
    for c in value:
        if ord(c) < 32 or ord(c) == 127:
            return True
        if c.isspace() and not allow_space:
            return True
    return False


def validate_remote(share_type: str, value: str) -> str:
    remote = value or ""
    if not remote or remote.startswith("-"):
        raise ShareError("remote must not be empty or start with '-'")
    if _bad_char(remote):
        raise ShareError("remote must not contain whitespace or control characters")
    if share_type == "nfs" and not _NFS_RE.match(remote):
        raise ShareError("NFS remote must look like host:/path")
    if share_type == "smb" and not _SMB_RE.match(remote):
        raise ShareError("SMB remote must look like //host/share")
    return remote


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or path.is_relative_to(parent)


def validate_mount_point(
    value: str,
    data_dir: Optional[str] = None,
    folders: Optional[list] = None,
) -> str:
    """Return the normalised mount point or raise ShareError.

    ``folders`` are download folders the mount point must not be, or be
    inside; pass them when they are known (share creation).
    """
    mp = value or ""
    if _bad_char(mp, allow_space=True):
        raise ShareError("mount_point must not contain control characters")
    if not os.path.isabs(mp):
        raise ShareError("mount_point must be an absolute path")
    if ".." in mp.split("/"):
        raise ShareError("mount_point must not contain '..'")
    mp = os.path.normpath(mp)
    if mp.startswith("//"):  # normpath keeps a leading double slash
        mp = "/" + mp.lstrip("/")

    base = shares_base()
    try:
        real = Path(os.path.realpath(mp))
        real_base = Path(os.path.realpath(base))
        data = Path(os.path.realpath(data_dir or DATA_DIR))
        real_folders = [Path(os.path.realpath(f)) for f in (folders or []) if f]
    except (OSError, ValueError):
        raise ShareError("mount_point is not a usable path")

    for candidate, root in ((Path(mp), Path(base)), (real, real_base)):
        if candidate == root or not candidate.is_relative_to(root):
            raise ShareError(
                f"mount_point must be a folder inside the shares base directory {base}"
            )
    for candidate in (Path(mp), real):
        if _inside(candidate, data) or data.is_relative_to(candidate):
            raise ShareError("mount_point must not overlap the app data directory")
        for folder in real_folders:
            if _inside(candidate, folder) or folder.is_relative_to(candidate):
                raise ShareError("mount_point must not be or contain a download folder")
    return mp


def validate_credential(label: str, value: Optional[str]) -> Optional[str]:
    if value is None:
        return value
    if any(c in value for c in ("\n", "\r", ",", "\0")):
        raise ShareError(f"{label} must not contain newlines, commas or NUL")
    return value


def validate_options(value: Optional[str]) -> Optional[str]:
    if value is None:
        return value
    text = value.strip()
    if not text:
        return text
    for item in text.split(","):
        key, sep, val = item.partition("=")
        if key not in ALLOWED_OPTIONS:
            raise ShareError(f"mount option {key!r} is not allowed")
        if ALLOWED_OPTIONS[key]:
            if not sep or not _VALUE_RE.match(val):
                raise ShareError(f"mount option {key} needs a simple value")
        elif sep:
            raise ShareError(f"mount option {key} takes no value")
    return text
