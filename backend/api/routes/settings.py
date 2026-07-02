from fastapi import APIRouter, HTTPException

from models.database import AsyncSessionLocal, SettingsModel
from models.schemas import SettingsResponse, SettingsUpdate
from services.cookies import (
    clear_cookies_file,
    validate_cookies_content,
    write_cookies_file,
)

router = APIRouter()


def _to_response(row: SettingsModel) -> SettingsResponse:
    return SettingsResponse(
        download_folder=row.download_folder,
        audio_format=row.audio_format,
        concurrent_downloads=row.concurrent_downloads,
        ytdlp_path=row.ytdlp_path,
        ffmpeg_path=row.ffmpeg_path,
        cookies_configured=bool(row.cookies_content or row.cookies_file_path),
        cookies_file_path=row.cookies_file_path,
    )


@router.get("/settings", response_model=SettingsResponse)
async def get_settings():
    async with AsyncSessionLocal() as session:
        row = await session.get(SettingsModel, 1)
        if row is None:
            row = SettingsModel(id=1)
            session.add(row)
            await session.commit()
        return _to_response(row)


@router.post("/settings", response_model=SettingsResponse)
async def update_settings(update: SettingsUpdate):
    async with AsyncSessionLocal() as session:
        row = await session.get(SettingsModel, 1)
        if row is None:
            row = SettingsModel(id=1)
            session.add(row)

        data = update.model_dump(exclude_unset=True)

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

        for key, value in data.items():
            if value is not None:
                setattr(row, key, value)
        await session.commit()
        await session.refresh(row)
        return _to_response(row)
