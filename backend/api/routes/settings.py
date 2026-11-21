import asyncio

from fastapi import APIRouter, HTTPException

from models.database import AsyncSessionLocal, SettingsModel
from models.schemas import SettingsResponse, SettingsUpdate
from services.cookies import (
    clear_cookies_file,
    validate_cookies_content,
    write_cookies_file,
)
from services.settings_guard import (
    SettingsError,
    validate_cookies_file_path,
    validate_ffmpeg_path,
    validate_folder,
    validate_ytdlp_path,
)

router = APIRouter()

_FOLDER_FIELDS = {
    "download_folder": "Download folder",
    "audio_download_folder": "Audio download folder",
}

# yt-dlp version per binary path, resolved once per process (the entrypoint
# updates yt-dlp at container start, so it can't change mid-run).
_version_cache: dict[str, str | None] = {}


async def _get_ytdlp_version(ytdlp_path: str) -> str | None:
    if ytdlp_path not in _version_cache:
        try:
            proc = await asyncio.create_subprocess_exec(
                ytdlp_path,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            version = stdout.decode(errors="replace").strip()
            _version_cache[ytdlp_path] = version if proc.returncode == 0 else None
        except (OSError, asyncio.TimeoutError):
            _version_cache[ytdlp_path] = None
    return _version_cache[ytdlp_path]


async def _to_response(row: SettingsModel) -> SettingsResponse:
    return SettingsResponse(
        download_folder=row.download_folder,
        audio_download_folder=row.audio_download_folder,
        audio_format=row.audio_format,
        concurrent_downloads=row.concurrent_downloads,
        ytdlp_path=row.ytdlp_path,
        ffmpeg_path=row.ffmpeg_path,
        cookies_configured=bool(row.cookies_content or row.cookies_file_path),
        cookies_file_path=row.cookies_file_path,
        ytdlp_version=await _get_ytdlp_version(row.ytdlp_path),
    )


@router.get("/settings", response_model=SettingsResponse)
async def get_settings():
    async with AsyncSessionLocal() as session:
        row = await session.get(SettingsModel, 1)
        if row is None:
            row = SettingsModel(id=1)
            session.add(row)
            await session.commit()
        return await _to_response(row)


@router.post("/settings", response_model=SettingsResponse)
async def update_settings(update: SettingsUpdate):
    async with AsyncSessionLocal() as session:
        row = await session.get(SettingsModel, 1)
        if row is None:
            row = SettingsModel(id=1)
            session.add(row)

        data = update.model_dump(exclude_unset=True)

        # Check the values that decide which files and programs the app
        # touches before anything is stored or written. A value equal to the
        # stored one is not a change and is left alone, so the settings page
        # (which posts every field) keeps working on an older setup.
        try:
            for field, label in _FOLDER_FIELDS.items():
                if data.get(field) is None:
                    continue
                value = data[field].strip()
                if field == "audio_download_folder" and not value:
                    continue  # "" clears it, handled below
                if value != getattr(row, field):
                    value = validate_folder(value, label)
                data[field] = value
            if data.get("ytdlp_path") is not None:
                value = data["ytdlp_path"].strip()
                if value != row.ytdlp_path:
                    value = validate_ytdlp_path(value)
                data["ytdlp_path"] = value
            if data.get("ffmpeg_path") is not None:
                value = data["ffmpeg_path"].strip()
                if value != row.ffmpeg_path:
                    value = validate_ffmpeg_path(value)
                data["ffmpeg_path"] = value
            if data.get("cookies_file_path"):
                value = data["cookies_file_path"].strip()
                if value and value != row.cookies_file_path:
                    value = validate_cookies_file_path(value)
                data["cookies_file_path"] = value
        except SettingsError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        # Cookie fields support "clear" via empty string, which the generic
        # not-None loop below cannot express.
        if "cookies_content" in data:
            content = (data.pop("cookies_content") or "").strip()
            if content:
                if not validate_cookies_content(content):
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Cookies must be in Netscape cookies.txt format "
                            "(export them with a 'Get cookies.txt' browser extension)."
                        ),
                    )
                row.cookies_content = content
                write_cookies_file(content)
            else:
                row.cookies_content = None
                clear_cookies_file()
        if "cookies_file_path" in data:
            path = (data.pop("cookies_file_path") or "").strip()
            row.cookies_file_path = path or None
        # Same "" = clear handling: an empty audio folder means "use the
        # default download folder", not a literal empty path.
        if "audio_download_folder" in data:
            folder = (data.pop("audio_download_folder") or "").strip()
            row.audio_download_folder = folder or None

        for key, value in data.items():
            if value is not None:
                setattr(row, key, value)
        await session.commit()
        await session.refresh(row)
        return await _to_response(row)
