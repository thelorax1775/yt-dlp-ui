"""Browse and manage files inside the configured download folder.

All operations are confined to the download root. Every user-supplied path is
resolved with `os.path.realpath` and checked to stay within the root, so `..`
traversal and absolute paths cannot escape the download directory.

Symbolic links: listing, downloading and creating folders follow links and
refuse any that lead outside the root. Delete and rename act on the link
itself (never on what it points to); only the folder the link sits in has to
be inside the root.
"""

import os
import shutil
import stat as stat_module
from datetime import datetime
from pathlib import Path

from models.database import AsyncSessionLocal, SettingsModel
from models.schemas import FileEntry, FileListResponse

_OUTSIDE = "Path is outside the download directory"


async def get_root() -> str:
    async with AsyncSessionLocal() as session:
        settings = await session.get(SettingsModel, 1)
        return settings.download_folder if settings else "/downloads"


def _safe_join(root: str, rel: str) -> str:
    """Resolve `rel` under `root`; raise ValueError if it escapes root."""
    root_real = Path(os.path.realpath(root))
    rel = (rel or "").lstrip("/\\")
    target = Path(os.path.realpath(root_real / rel))
    if not target.is_relative_to(root_real):
        raise ValueError(_OUTSIDE)
    return str(target)


def _safe_entry(root: str, rel: str) -> str:
    """Like `_safe_join`, but the last path component is not resolved.

    The folder holding the entry is resolved and must be inside root; the
    entry itself is returned as it is on disk, so a symbolic link stays a
    link. Used by delete and rename, which must act on the link.
    """
    rel = (rel or "").lstrip("/\\").rstrip("/")
    parent_rel, name = os.path.split(rel)
    if name in ("", ".", ".."):
        return _safe_join(root, rel)
    return os.path.join(_safe_join(root, parent_rel), name)


def _rel_path(root: str, target: str) -> str:
    """Path of `target` relative to the root, without resolving `target`."""
    rel = os.path.relpath(target, os.path.realpath(root))
    return "" if rel == "." else rel.replace(os.sep, "/")


def _entry(root: str, full: str) -> FileEntry:
    """Describe one entry. A link is described by what it points to; a link
    whose target is gone is still described, so it can be removed."""
    try:
        info = os.stat(full)
    except OSError:
        info = os.lstat(full)
    is_dir = stat_module.S_ISDIR(info.st_mode)
    return FileEntry(
        name=os.path.basename(full),
        path=_rel_path(root, full),
        is_dir=is_dir,
        size=None if is_dir else info.st_size,
        modified=datetime.fromtimestamp(info.st_mtime),
    )


async def list_dir(rel: str = "") -> FileListResponse:
    root = await get_root()
    root_real = os.path.realpath(root)
    target = _safe_join(root, rel)

    entries: list[FileEntry] = []
    if os.path.isdir(target):
        for name in sorted(os.listdir(target), key=str.lower):
            try:
                entries.append(_entry(root, os.path.join(target, name)))
            except OSError:
                continue

    # directories first, then files
    entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))
    return FileListResponse(
        root=root_real,
        path=_rel_path(root, target),
        entries=entries,
    )


async def delete_path(rel: str) -> None:
    root = await get_root()
    target = _safe_entry(root, rel)
    if target == os.path.realpath(root):
        raise ValueError("Cannot delete the download root")
    if not os.path.lexists(target):
        raise FileNotFoundError("File not found")
    if os.path.isdir(target) and not os.path.islink(target):
        shutil.rmtree(target)
    else:
        # Files and links (also links to folders): remove the entry only.
        os.remove(target)


async def rename_path(rel: str, new_name: str) -> FileEntry:
    root = await get_root()
    target = _safe_entry(root, rel)
    if target == os.path.realpath(root):
        raise ValueError("Cannot rename the download root")
    if not os.path.lexists(target):
        raise FileNotFoundError("File not found")
    separators = {os.sep, os.altsep or os.sep, "/", "\\"}
    if not new_name or new_name in (".", "..") or any(s in new_name for s in separators):
        raise ValueError("Invalid file name")
    # Same (resolved, inside-root) folder, new name: cannot leave the root.
    dest = os.path.join(os.path.dirname(target), new_name)
    if os.path.lexists(dest):
        raise ValueError("A file with that name already exists")
    os.rename(target, dest)
    return _entry(root, dest)


async def make_dir(rel: str, name: str) -> FileEntry:
    root = await get_root()
    parent = _safe_join(root, rel)
    target = _safe_join(root, _rel_path(root, os.path.join(parent, name)))
    os.makedirs(target, exist_ok=False)
    return _entry(root, target)


async def resolve_for_download(rel: str) -> str:
    """Return an absolute path to a file for serving, validated under root."""
    root = await get_root()
    target = _safe_join(root, rel)
    if not os.path.isfile(target):
        raise FileNotFoundError("File not found")
    return target
