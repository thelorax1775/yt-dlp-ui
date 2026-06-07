import asyncio
import json
import logging
from typing import Optional

from models.database import AsyncSessionLocal, SettingsModel
from models.schemas import FormatInfo, MetadataResponse

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
    for f in raw.get("formats", []):
        formats.append(
            FormatInfo(
                format_id=f.get("format_id", ""),
                ext=f.get("ext", ""),
                resolution=f.get("resolution"),
                fps=f.get("fps"),
                vcodec=f.get("vcodec"),
                acodec=f.get("acodec"),
                filesize=f.get("filesize") or f.get("filesize_approx"),
                format_note=f.get("format_note"),
            )
        )

    return MetadataResponse(
        title=raw.get("title", "Unknown"),
        thumbnail=raw.get("thumbnail"),
        uploader=raw.get("uploader") or raw.get("channel"),
        duration=raw.get("duration"),
        url=url,
        formats=formats,
    )
