from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from models.schemas import SearchResponse
from services.search import search as run_search

router = APIRouter()


@router.get("/search", response_model=SearchResponse)
async def search(
    q: Optional[str] = Query(None, description="Search query"),
    channel: Optional[str] = Query(None, description="Channel URL or @handle"),
    limit: int = Query(5, description="Max results, 1-10"),
    latest_from_channel: bool = Query(
        False, description="Resolve q to a channel, then list its newest videos"
    ),
):
    if not q and not channel:
        raise HTTPException(status_code=400, detail="Provide either 'q' or 'channel'")
    try:
        return await run_search(
            query=q, channel=channel, limit=limit, latest_from_channel=latest_from_channel
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Search failed: {exc}")
