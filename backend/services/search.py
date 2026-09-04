import asyncio
import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_HANDLE_RE = re.compile(r"^@?[A-Za-z0-9._-]{2,30}$")


def search_args(
    ytdlp_path: str,
    cookie_args: list[str],
    *,
    query: Optional[str] = None,
    channel_url: Optional[str] = None,
    limit: int = 5,
) -> list[str]:
    """Build the yt-dlp argv for a search-style (--flat-playlist) listing."""
    base = [ytdlp_path, "--dump-single-json", "--flat-playlist", "--no-warnings", *cookie_args]

    if channel_url is not None:
        target = channel_url.rstrip("/")
        if not target.endswith("/videos"):
            target = f"{target}/videos"
        return [*base, "--playlist-end", str(limit), target]

    return [*base, f"ytsearch{limit}:{query}"]


def parse_flat_entries(raw: dict) -> list[dict]:
    """Turn yt-dlp's --flat-playlist JSON into plain result rows."""
    rows: list[dict] = []
    for entry in raw.get("entries") or []:
        vid = entry.get("id")
        if not vid:
            continue
        url = entry.get("url")
        if not (isinstance(url, str) and url.startswith(("http://", "https://"))):
            url = f"https://www.youtube.com/watch?v={vid}"
        rows.append(
            {
                "id": vid,
                "title": entry.get("title") or "",
                "url": url,
                "uploader": entry.get("uploader") or entry.get("channel"),
                "channel_url": entry.get("channel_url") or entry.get("uploader_url"),
                "duration": entry.get("duration"),
                "upload_date": entry.get("upload_date"),
                "view_count": entry.get("view_count"),
            }
        )
    return rows


def normalize_channel(value: str) -> str:
    """Accept a channel URL or bare handle and return a canonical channel URL."""
    v = value.strip()

    if v.startswith(("http://", "https://")):
        if "youtube.com" not in v and "youtu.be" not in v:
            raise ValueError(f"not a youtube channel URL: {value}")
        return v.rstrip("/")

    if _HANDLE_RE.match(v):
        handle = v if v.startswith("@") else f"@{v}"
        return f"https://www.youtube.com/{handle}"

    raise ValueError(f"not a youtube channel URL or handle: {value}")


def iso_date(s: Optional[str]) -> Optional[str]:
    """Convert yt-dlp's YYYYMMDD to YYYY-MM-DD; None/malformed -> None."""
    if not s or not isinstance(s, str) or len(s) != 8 or not s.isdigit():
        return None
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


async def run_ytdlp_json(args: list[str]) -> dict:
    from services.metadata import extract_error  # lazy: metadata imports the DB layer

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = extract_error(stderr.decode(errors="replace"))
        raise ValueError(f"yt-dlp failed: {err}")

    return json.loads(stdout.decode(errors="replace"))


async def enrich(
    entries: list[dict],
    ytdlp_path: str,
    cookie_args: list[str],
    *,
    concurrency: int = 1,  # a swapless 4 GB VM; yt-dlp+quickjs per video is heavy
) -> list[dict]:
    """Fill in upload_date/duration/uploader/title from full metadata, per entry."""
    sem = asyncio.Semaphore(concurrency)

    async def _fill(entry: dict) -> None:
        async with sem:
            args = [
                ytdlp_path,
                "--dump-single-json",
                "--no-playlist",
                "--no-warnings",
                *cookie_args,
                entry["url"],
            ]
            try:
                full = await run_ytdlp_json(args)
            except Exception:  # noqa: BLE001
                logger.warning("enrich failed for %s", entry.get("url"), exc_info=True)
                return
            entry["upload_date"] = full.get("upload_date") or entry.get("upload_date")
            entry["duration"] = full.get("duration") or entry.get("duration")
            entry["uploader"] = full.get("uploader") or full.get("channel") or entry.get("uploader")
            entry["title"] = full.get("title") or entry.get("title")

    await asyncio.gather(*(_fill(e) for e in entries))
    return entries


async def search(
    query: Optional[str] = None,
    channel: Optional[str] = None,
    limit: int = 5,
    latest_from_channel: bool = False,
) -> dict:
    from services.cookies import resolve_cookies_args
    from services.metadata import _get_settings

    settings = await _get_settings()
    ytdlp_path = settings.ytdlp_path if settings else "yt-dlp"
    cookie_args = resolve_cookies_args(settings)

    limit = max(1, min(10, limit))

    if channel is not None:
        channel_url = normalize_channel(channel)
        args = search_args(ytdlp_path, cookie_args, channel_url=channel_url, limit=limit)
        raw = await run_ytdlp_json(args)
        entries = parse_flat_entries(raw)
        entries = await enrich(entries, ytdlp_path, cookie_args)
        entries = _finalize(entries, sort_newest=True)
        return {"mode": "channel", "channel": channel_url, "results": entries}

    if latest_from_channel:
        probe_args = search_args(ytdlp_path, cookie_args, query=query, limit=3)
        raw = await run_ytdlp_json(probe_args)
        probe_entries = parse_flat_entries(raw)
        channel_url = probe_entries[0].get("channel_url") if probe_entries else None
        uploader = probe_entries[0].get("uploader") if probe_entries else None
        if not channel_url:
            raise ValueError("no channel found for that query")

        args = search_args(ytdlp_path, cookie_args, channel_url=channel_url, limit=limit)
        raw = await run_ytdlp_json(args)
        entries = parse_flat_entries(raw)
        entries = await enrich(entries, ytdlp_path, cookie_args)
        entries = _finalize(entries, sort_newest=True)
        return {
            "mode": "channel",
            "channel": channel_url,
            "resolved_channel": {"name": uploader, "url": channel_url},
            "results": entries,
        }

    args = search_args(ytdlp_path, cookie_args, query=query, limit=limit)
    raw = await run_ytdlp_json(args)
    entries = parse_flat_entries(raw)
    entries = await enrich(entries, ytdlp_path, cookie_args)
    entries = _finalize(entries, sort_newest=False)
    return {"mode": "search", "query": query, "results": entries}


def _finalize(entries: list[dict], *, sort_newest: bool) -> list[dict]:
    """Convert upload_date to YYYY-MM-DD, then optionally sort newest first (None last)."""
    for e in entries:
        e["upload_date"] = iso_date(e.get("upload_date"))
    if sort_newest:
        dated = sorted(
            (e for e in entries if e.get("upload_date") is not None),
            key=lambda e: e["upload_date"],
            reverse=True,
        )
        undated = [e for e in entries if e.get("upload_date") is None]
        entries = dated + undated
    return entries
