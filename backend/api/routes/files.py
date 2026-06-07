import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from models.schemas import (
    FileEntry,
    FileListResponse,
    MkdirRequest,
    RenameRequest,
)
from services import files_manager

router = APIRouter()


@router.get("/files", response_model=FileListResponse)
async def list_files(path: str = Query("", description="Path relative to download root")):
    try:
        return await files_manager.list_dir(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/files")
async def delete_file(path: str = Query(..., description="Path relative to download root")):
    try:
        await files_manager.delete_path(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    return {"status": "deleted", "path": path}


@router.post("/files/rename", response_model=FileEntry)
async def rename_file(req: RenameRequest):
    try:
        return await files_manager.rename_path(req.path, req.new_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")


@router.post("/files/mkdir", response_model=FileEntry)
async def make_dir(req: MkdirRequest):
    try:
        return await files_manager.make_dir(req.path, req.name)
    except FileExistsError:
        raise HTTPException(status_code=400, detail="Folder already exists")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/files/download")
async def download_file(path: str = Query(..., description="Path relative to download root")):
    try:
        abs_path = await files_manager.resolve_for_download(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(abs_path, filename=os.path.basename(abs_path))
