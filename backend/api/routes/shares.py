from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from models.database import AsyncSessionLocal, ShareModel
from models.schemas import MountResult, ShareCreate, ShareResponse
from services import share_manager

router = APIRouter()


def _to_response(row: ShareModel) -> ShareResponse:
    return ShareResponse(
        id=row.id,
        name=row.name,
        type=row.type,
        remote=row.remote,
        mount_point=row.mount_point,
        username=row.username,
        domain=row.domain,
        options=row.options,
        auto_mount=bool(row.auto_mount),
        mounted=share_manager.is_mounted(row.mount_point),
    )


@router.get("/shares", response_model=list[ShareResponse])
async def list_shares():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ShareModel).order_by(ShareModel.id))
        return [_to_response(r) for r in result.scalars().all()]


@router.post("/shares", response_model=ShareResponse)
async def create_share(share: ShareCreate):
    async with AsyncSessionLocal() as session:
        row = ShareModel(
            name=share.name,
            type=share.type,
            remote=share.remote,
            mount_point=share.mount_point,
            username=share.username,
            password=share.password,
            domain=share.domain,
            options=share.options,
            auto_mount=1 if share.auto_mount else 0,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return _to_response(row)


@router.delete("/shares/{share_id}")
async def delete_share(share_id: int):
    async with AsyncSessionLocal() as session:
        row = await session.get(ShareModel, share_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Share not found")
        # best-effort unmount before removing
        await share_manager.unmount_share(row.mount_point)
        await session.delete(row)
        await session.commit()
    return {"status": "deleted", "id": share_id}


@router.post("/shares/{share_id}/mount", response_model=MountResult)
async def mount_share(share_id: int):
    async with AsyncSessionLocal() as session:
        row = await session.get(ShareModel, share_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Share not found")
        ok, msg = await share_manager.mount_share(row)
    return MountResult(mounted=ok, message=msg)


@router.post("/shares/{share_id}/unmount", response_model=MountResult)
async def unmount_share(share_id: int):
    async with AsyncSessionLocal() as session:
        row = await session.get(ShareModel, share_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Share not found")
        _ok, msg = await share_manager.unmount_share(row.mount_point)
        still_mounted = share_manager.is_mounted(row.mount_point)
    return MountResult(mounted=still_mounted, message=msg)
