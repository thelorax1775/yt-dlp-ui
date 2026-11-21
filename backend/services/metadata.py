import asyncio
import json
import logging
import os
import signal
from typing import Optional

from models.database import AsyncSessionLocal, SettingsModel
from models.schemas import FormatInfo, MetadataResponse, ResolutionOption
from services.cookies import resolve_cookies_args

logger = logging.getLogger(__name__)

# A title/info lookup that takes longer than this is killed. Read at call time,
# so tests can lower it.
LOOKUP_TIMEOUT_SECONDS = 60


class LookupTimeout(Exception):
    """The yt-dlp lookup ran past LOOKUP_TIMEOUT_SECONDS and was killed."""


class LookupCancelled(Exception):
    """The lookup was cancelled and its process killed."""


def kill_process(proc) -> None:
    """SIGKILL the process and anything it started (it leads its own session)."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
        return
    except (ProcessLookupError, PermissionError, TypeError, AttributeError):
        pass
    try:
        proc.kill()
    except (ProcessLookupError, AttributeError):
        pass


async def run_lookup(args, cancel_event: Optional[asyncio.Event] = None, on_start=None):
    """Run a yt-dlp lookup; return (returncode, stdout, stderr).

    Raises LookupTimeout after LOOKUP_TIMEOUT_SECONDS and LookupCancelled once
    ``cancel_event`` is set. In both cases, and when the calling task is
    cancelled, the process is killed and reaped before this returns.
    """
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    if on_start:
        on_start(proc)
    work = asyncio.ensure_future(proc.communicate())
    waiters = {work}
    cancel_wait = None
    if cancel_event is not None:
        cancel_wait = asyncio.ensure_future(cancel_event.wait())
        waiters.add(cancel_wait)
    try:
        done, _ = await asyncio.wait(
            waiters, timeout=LOOKUP_TIMEOUT_SECONDS, return_when=asyncio.FIRST_COMPLETED
        )
        if work in done:
            stdout, stderr = work.result()
            return proc.returncode, stdout, stderr
        if cancel_wait is not None and cancel_wait in done:
            raise LookupCancelled()
        raise LookupTimeout(
            f"title lookup timed out after {LOOKUP_TIMEOUT_SECONDS} s and was stopped"
        )
    finally:
        if not work.done():
            kill_process(proc)
            work.cancel()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                pass
        if cancel_wait is not None:
            cancel_wait.cancel()


async def _get_settings() -> Optional[SettingsModel]:
    async with AsyncSessionLocal() as session:
        return await session.get(SettingsModel, 1)


def extract_error(output: str) -> str:
    """Pull the ERROR line(s) out of yt-dlp output, falling back to the tail."""
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    errors = [ln for ln in lines if ln.startswith("ERROR")]
    if errors:
        return "\n".join(errors[:5])
    return "\n".join(lines[-5:]) if lines else "unknown error"


async def fetch_metadata(url: str) -> MetadataResponse:
    settings = await _get_settings()
    ytdlp_path = settings.ytdlp_path if settings else "yt-dlp"
    args = [
        ytdlp_path,
        "--dump-single-json",
        "--no-playlist",
        "--no-warnings",
        *resolve_cookies_args(settings),
        url,
    ]

    try:
        returncode, stdout, stderr = await run_lookup(args)
    except LookupTimeout as exc:
        raise ValueError(f"yt-dlp failed: {exc}")

    if returncode != 0:
        err = extract_error(stderr.decode(errors="replace"))
        raise ValueError(f"yt-dlp failed: {err}")

    raw = json.loads(stdout.decode(errors="replace"))

    formats: list[FormatInfo] = []
    # best (largest) filesize seen per video height, for the resolution picker
    by_height: dict[int, dict] = {}

    for f in raw.get("formats", []):
        height = f.get("height")
        vcodec = f.get("vcodec")
        size = f.get("filesize") or f.get("filesize_approx")
        formats.append(
            FormatInfo(
                format_id=f.get("format_id", ""),
                ext=f.get("ext", ""),
                resolution=f.get("resolution"),
                height=height,
                fps=f.get("fps"),
                vcodec=vcodec,
                acodec=f.get("acodec"),
                filesize=size,
                format_note=f.get("format_note"),
            )
        )

        # Only count real video streams (skip audio-only / images)
        if height and vcodec and vcodec != "none":
            cur = by_height.get(height)
            if cur is None or (size or 0) > (cur.get("filesize") or 0):
                by_height[height] = {"ext": f.get("ext"), "filesize": size}

    resolutions = [
        ResolutionOption(
            height=h,
            label=f"{h}p",
            ext=by_height[h].get("ext"),
            filesize=by_height[h].get("filesize"),
        )
        for h in sorted(by_height.keys(), reverse=True)
    ]

    return MetadataResponse(
        title=raw.get("title") or "Unknown",
        thumbnail=raw.get("thumbnail"),
        uploader=raw.get("uploader") or raw.get("channel"),
        duration=raw.get("duration"),
        url=url,
        formats=formats,
        resolutions=resolutions,
    )
