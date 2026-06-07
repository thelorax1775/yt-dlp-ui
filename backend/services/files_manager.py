"""Browse and manage files inside the configured download folder.

All operations are confined to the download root. Every user-supplied path is
resolved with `os.path.realpath` and checked to stay within the root, so `..`
traversal and absolute paths cannot escape the download directory.
"""

import os
import shutil
from datetime import datetime

from models.database import AsyncSessionLocal, SettingsModel
from models.schemas import FileEntry, FileListResponse


async def get_root() -> str:
    async with AsyncSessionLocal() as session:
        settings = await session.get(SettingsModel, 1)
        return settings.download_folder if settings else "/downloads"


def _safe_join(root: str, rel: str) -> str:
    """Resolve `rel` under `root`; raise ValueError if it escapes root."""
    root_real = os.path.realpath(root)
    rel = (rel or "").lstrip("/\\")
    target = os.path.realpath(os.path.join(root_real, rel))
    if target != root_real and not target.startswith(root_real + os.sep):
        raise ValueError("Path is outside the download directory")
    return target


def _rel_path(root: str, target: str) -> str:
    root_real = os.path.realpath(root)
    rel = os.path.relpath(os.path.realpath(target), root_real)
    return "" if rel == "." else rel.replace(os.sep, "/")


async def list_dir(rel: str = "") -> FileListResponse:
    root = await get_root()
    root_real = os.path.realpath(root)
    target = _safe_join(root, rel)

    entries: list[FileEntry] = []
    if os.path.isdir(target):
        for name in sorted(os.listdir(target), key=str.lower):
            full = os.path.join(target, name)
            try:
                stat = os.stat(full)
                is_dir = os.path.isdir(full)
                entries.append(
                    FileEntry(
                        name=name,
                        path=_rel_path(root, full),
                        is_dir=is_dir,
                        size=None if is_dir else stat.st_size,
                        modified=datetime.fromtimestamp(stat.st_mtime),
                    )
                )
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
    target = _safe_join(root, rel)
    if os.path.realpath(target) == os.path.realpath(root):
        raise ValueError("Cannot delete the download root")
    if not os.path.exists(target):
        raise FileNotFoundError("File not found")
    if os.path.isdir(target):
        shutil.rmtree(target)
    else:
        os.remove(target)


async def rename_path(rel: str, new_name: str) -> FileEntry:
    root = await get_root()
    target = _safe_join(root, rel)
    if not os.path.exists(target):
        raise FileNotFoundError("File not found")
    dest = os.path.join(os.path.dirname(target), new_name)
    # ensure destination is still inside root
    dest = _safe_join(root, _rel_path(root, dest))
    if os.path.exists(dest):
        raise ValueError("A file with that name already exists")
    os.rename(target, dest)
    stat = os.stat(dest)
    is_dir = os.path.isdir(dest)
    return FileEntry(
        name=os.path.basename(dest),
        path=_rel_path(root, dest),
        is_dir=is_dir,
        size=None if is_dir else stat.st_size,
        modified=datetime.fromtimestamp(stat.st_mtime),
    )


async def make_dir(rel: str, name: str) -> FileEntry:
    root = await get_root()
    parent = _safe_join(root, rel)
    target = _safe_join(root, _rel_path(root, os.path.join(parent, name)))
    os.makedirs(target, exist_ok=False)
    stat = os.stat(target)
    return FileEntry(
        name=name,
        path=_rel_path(root, target),
        is_dir=True,
        size=None,
        modified=datetime.fromtimestamp(stat.st_mtime),
    )


async def resolve_for_download(rel: str) -> str:
    """Return an absolute path to a file for serving, validated under root."""
    root = await get_root()
    target = _safe_join(root, rel)
    if not os.path.isfile(target):
        raise FileNotFoundError("File not found")
    return target
