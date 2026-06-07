import asyncio
import json
import logging
from typing import Optional

from models.database import AsyncSessionLocal, SettingsModel
from models.schemas import FormatInfo, MetadataResponse, ResolutionOption

logger = logging.getLogger(__name__)


async def _get_ytdlp_path() -> str:
    async with AsyncSessionLocal() as session:
        settings = await session.get(SettingsModel, 1)
        return settings.ytdlp_path if settings else "yt-dlp"


async def fetch_metadata(url: str) -> MetadataResponse:
    ytdlp_path = await _get_ytdlp_path()
    args = [
        ytdlp_path,
        "--dump-single-json",
        "--no-playlist",
        "--no-warnings",
        url,
    ]

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
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
        title=raw.get("title", "Unknown"),
        thumbnail=raw.get("thumbnail"),
        uploader=raw.get("uploader") or raw.get("channel"),
        duration=raw.get("duration"),
        url=url,
        formats=formats,
        resolutions=resolutions,
    )
