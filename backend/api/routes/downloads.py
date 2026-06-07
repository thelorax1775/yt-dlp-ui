from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from models.schemas import DownloadRequest, JobResponse
from services.download_manager import manager

router = APIRouter()


@router.post("/download", response_model=JobResponse)
async def start_download(req: DownloadRequest):
    job = await manager.enqueue(req)
    return job.to_response()


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs():
    return manager.list_jobs()


@router.get("/jobs/stream")
async def stream_jobs():
    async def event_generator():
        async for data in manager.subscribe():
            yield {"data": data}

    return EventSourceResponse(event_generator())


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    ok = await manager.cancel(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "cancelled", "id": job_id}


@router.post("/jobs/{job_id}/retry", response_model=JobResponse)
async def retry_job(job_id: str):
    job = await manager.retry(job_id)
    if not job:
        raise HTTPException(status_code=400, detail="Job cannot be retried")
    return job.to_response()
