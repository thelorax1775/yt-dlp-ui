from fastapi import APIRouter
from sqlalchemy import select

from models.database import AsyncSessionLocal, HistoryModel
from models.schemas import HistoryEntry

router = APIRouter()


@router.get("/history", response_model=list[HistoryEntry])
async def get_history():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(HistoryModel).order_by(HistoryModel.finished_at.desc()).limit(200)
        )
        rows = result.scalars().all()
        return [
            HistoryEntry(
                id=r.id,
                url=r.url,
                title=r.title,
                thumbnail=r.thumbnail,
                file_path=r.file_path,
                format_id=r.format_id,
                finished_at=r.finished_at,
            )
            for r in rows
        ]
