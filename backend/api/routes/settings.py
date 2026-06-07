from fastapi import APIRouter

from models.database import AsyncSessionLocal, SettingsModel
from models.schemas import SettingsResponse, SettingsUpdate

router = APIRouter()


def _to_response(row: SettingsModel) -> SettingsResponse:
    return SettingsResponse(
        download_folder=row.download_folder,
        audio_format=row.audio_format,
        concurrent_downloads=row.concurrent_downloads,
        ytdlp_path=row.ytdlp_path,
        ffmpeg_path=row.ffmpeg_path,
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
        for key, value in data.items():
            if value is not None:
                setattr(row, key, value)
        await session.commit()
        await session.refresh(row)
        return _to_response(row)
