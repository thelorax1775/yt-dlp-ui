from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, func, select

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


@router.delete("/history/{entry_id}")
async def delete_history_entry(entry_id: str):
    async with AsyncSessionLocal() as session:
        row = await session.get(HistoryModel, entry_id)
        if row is None:
            raise HTTPException(status_code=404, detail="History entry not found")
        await session.delete(row)
        await session.commit()
    return {"status": "deleted", "id": entry_id}


@router.delete("/history")
async def clear_history():
    async with AsyncSessionLocal() as session:
        count_result = await session.execute(select(func.count()).select_from(HistoryModel))
        count = count_result.scalar_one()
        await session.execute(delete(HistoryModel))
        await session.commit()
    return {"status": "cleared", "count": count}
