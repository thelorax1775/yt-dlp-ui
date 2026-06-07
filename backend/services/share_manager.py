"""Mount/unmount NFS and SMB (CIFS) network shares.

Mounts are performed with `mount`/`umount` via subprocess using an explicit
argument list (never a shell), so user-supplied values cannot inject shell
commands. Mounting requires the process to have privileges (root or
CAP_SYS_ADMIN); when running in Docker the backend container needs
`cap_add: [SYS_ADMIN]` and `cifs-utils` / `nfs-common` installed.
"""

import asyncio
import logging
import os
import stat
import tempfile

from models.database import ShareModel

logger = logging.getLogger(__name__)

_CREDS_DIR = "/tmp/ytdlp-share-creds"


async def _run(args: list[str]) -> tuple[int, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError:
        return 127, f"command not found: {args[0]} (is it installed?)"
    out, _ = await proc.communicate()
    return proc.returncode, out.decode(errors="replace").strip()


def is_mounted(mount_point: str) -> bool:
    """Return True if `mount_point` is an active mount point."""
    target = os.path.abspath(mount_point)
    try:
        with open("/proc/mounts", "r", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 2 and parts[1] == target:
                    return True
    except FileNotFoundError:
        # /proc/mounts not available (e.g. non-Linux dev host)
        return False
    return False


def _write_credentials(share: ShareModel) -> str:
    """Write an SMB credentials file with 0600 perms; return its path."""
    os.makedirs(_CREDS_DIR, exist_ok=True)
    os.chmod(_CREDS_DIR, stat.S_IRWXU)
    fd, path = tempfile.mkstemp(prefix=f"share-{share.id}-", dir=_CREDS_DIR)
    with os.fdopen(fd, "w") as fh:
        fh.write(f"username={share.username or ''}\n")
        fh.write(f"password={share.password or ''}\n")
        if share.domain:
            fh.write(f"domain={share.domain}\n")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return path


def _build_mount_args(share: ShareModel) -> list[str]:
    os.makedirs(share.mount_point, exist_ok=True)
    extra = (share.options or "").strip()

    if share.type == "smb":
        opts = ["rw", "iocharset=utf8"]
        if share.username:
            creds = _write_credentials(share)
            opts.append(f"credentials={creds}")
        else:
            opts.append("guest")
        if extra:
            opts.append(extra)
        return [
            "mount", "-t", "cifs",
            share.remote, share.mount_point,
            "-o", ",".join(opts),
        ]

    # nfs
    opts = extra if extra else "rw,soft,timeo=30"
    return [
        "mount", "-t", "nfs",
        share.remote, share.mount_point,
        "-o", opts,
    ]


async def mount_share(share: ShareModel) -> tuple[bool, str]:
    if is_mounted(share.mount_point):
        return True, "Already mounted"
    args = _build_mount_args(share)
    code, output = await _run(args)
    if code == 0:
        return True, "Mounted"
    logger.warning("mount failed for share %s: %s", share.id, output)
    return False, output or f"mount exited with code {code}"


async def unmount_share(mount_point: str) -> tuple[bool, str]:
    if not is_mounted(mount_point):
        return True, "Not mounted"
    code, output = await _run(["umount", mount_point])
    if code == 0:
        return True, "Unmounted"
    return False, output or f"umount exited with code {code}"


async def auto_mount_all() -> None:
    """Mount every share flagged auto_mount on startup (best effort)."""
    from models.database import AsyncSessionLocal
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ShareModel).where(ShareModel.auto_mount == 1)
        )
        shares = result.scalars().all()

    for share in shares:
        try:
            ok, msg = await mount_share(share)
            logger.info("auto-mount %s: %s (%s)", share.name, ok, msg)
        except Exception:  # noqa: BLE001
            logger.exception("auto-mount failed for %s", share.name)
