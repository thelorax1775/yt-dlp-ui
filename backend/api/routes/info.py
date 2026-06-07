from fastapi import APIRouter, HTTPException, Query

from models.schemas import MetadataResponse
from services.metadata import fetch_metadata

router = APIRouter()


@router.get("/info", response_model=MetadataResponse)
async def get_info(url: str = Query(..., description="Video or playlist URL")):
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
    try:
        return await fetch_metadata(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to fetch metadata: {exc}")
