import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime
from typing import AsyncGenerator, Optional

from models.database import (
    AsyncSessionLocal,
    HistoryModel,
    JobModel,
    SettingsModel,
)
from models.schemas import DownloadRequest, JobResponse

logger = logging.getLogger(__name__)

# Compact one-line progress template emitted by yt-dlp per tick.
PROGRESS_TEMPLATE = (
    "PROGRESS %(progress.status)s %(progress._percent_str)s "
    "%(progress._speed_str)s %(progress._eta_str)s"
)

PROGRESS_RE = re.compile(
    r"^PROGRESS\s+(\S+)\s+([\d.]+)%\s+(\S+)\s+(\S+)\s*$"
)

# yt-dlp prints the final merged/destination path with these markers.
DEST_RE = re.compile(r"\[(?:download|Merger|ExtractAudio)\].*?(?:Destination:|to|into)\s+\"?(.+?)\"?$")


class Job:
    """In-memory representation of a download job."""

    def __init__(self, url: str, format_id: Optional[str]):
        self.id = str(uuid.uuid4())
        self.url = url
        self.format_id = format_id
        self.title: Optional[str] = None
        self.thumbnail: Optional[str] = None
        self.status = "queued"
        self.progress = 0.0
        self.speed: Optional[str] = None
        self.eta: Optional[str] = None
        self.file_path: Optional[str] = None
        self.error: Optional[str] = None
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def to_response(self) -> JobResponse:
        return JobResponse(
            id=self.id,
            url=self.url,
            title=self.title,
            thumbnail=self.thumbnail,
            status=self.status,
            format_id=self.format_id,
            progress=self.progress,
            speed=self.speed,
            eta=self.eta,
            file_path=self.file_path,
            error=self.error,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    def to_dict(self) -> dict:
        return self.to_response().model_dump(mode="json")


class DownloadManager:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._jobs: dict[str, Job] = {}
        self._subscribers: list[asyncio.Queue] = []
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._workers: list[asyncio.Task] = []
        self._running = False

    # ---------- lifecycle ----------

    async def start(self) -> None:
        self._running = True
        concurrency = await self._get_concurrency()
        for _ in range(concurrency):
            self._workers.append(asyncio.create_task(self._worker()))
        logger.info("DownloadManager started with %d workers", concurrency)

    async def stop(self) -> None:
        self._running = False
        for proc in self._processes.values():
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
        for w in self._workers:
            w.cancel()
        self._workers.clear()

    async def _get_concurrency(self) -> int:
        async with AsyncSessionLocal() as session:
            settings = await session.get(SettingsModel, 1)
            return settings.concurrent_downloads if settings else 2

    async def _get_settings(self) -> SettingsModel:
        async with AsyncSessionLocal() as session:
            return await session.get(SettingsModel, 1)

    # ---------- public API ----------

    async def enqueue(self, req: DownloadRequest) -> Job:
        job = Job(url=req.url, format_id=req.format_id)
        self._jobs[job.id] = job
        self._cancel_events[job.id] = asyncio.Event()
        await self._persist_job(job)
        await self._queue.put(job)
        await self._broadcast(job)
        return job

    async def retry(self, job_id: str) -> Optional[Job]:
        old = self._jobs.get(job_id)
        if not old or old.status not in ("failed", "cancelled"):
            return None
        old.status = "queued"
        old.progress = 0.0
        old.speed = None
        old.eta = None
        old.error = None
        old.updated_at = datetime.utcnow()
        self._cancel_events[job_id] = asyncio.Event()
        await self._persist_job(old)
        await self._queue.put(old)
        await self._broadcast(old)
        return old

    async def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        event = self._cancel_events.get(job_id)
        if event:
            event.set()
        proc = self._processes.get(job_id)
        if proc:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
        if job.status in ("queued", "downloading"):
            job.status = "cancelled"
            job.updated_at = datetime.utcnow()
            await self._persist_job(job)
            await self._broadcast(job)
        return True

    def list_jobs(self) -> list[JobResponse]:
        return [j.to_response() for j in sorted(
            self._jobs.values(), key=lambda x: x.created_at, reverse=True
        )]

    async def subscribe(self) -> AsyncGenerator[str, None]:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        try:
            # send current snapshot immediately
            for job in self._jobs.values():
                await q.put(job.to_dict())
            while True:
                data = await q.get()
                yield json.dumps(data)
        finally:
            self._subscribers.remove(q)

    # ---------- internals ----------

    async def _broadcast(self, job: Job) -> None:
        payload = job.to_dict()
        for q in list(self._subscribers):
            await q.put(payload)

    async def _persist_job(self, job: Job) -> None:
        async with AsyncSessionLocal() as session:
            row = await session.get(JobModel, job.id)
            if row is None:
                row = JobModel(id=job.id)
                session.add(row)
            row.url = job.url
            row.title = job.title
            row.thumbnail = job.thumbnail
            row.status = job.status
            row.format_id = job.format_id
            row.progress = job.progress
            row.speed = job.speed
            row.eta = job.eta
            row.file_path = job.file_path
            row.error = job.error
            row.created_at = job.created_at
            row.updated_at = job.updated_at
            await session.commit()

    async def _write_history(self, job: Job) -> None:
        async with AsyncSessionLocal() as session:
            session.add(
                HistoryModel(
                    id=job.id,
                    url=job.url,
                    title=job.title,
                    thumbnail=job.thumbnail,
                    file_path=job.file_path,
                    format_id=job.format_id,
                    finished_at=datetime.utcnow(),
                )
            )
            await session.commit()

    def _build_args(self, job: Job, settings: SettingsModel) -> list[str]:
        output_template = os.path.join(settings.download_folder, "%(title)s.%(ext)s")
        args = [
            settings.ytdlp_path,
            "--no-playlist",
            "--newline",
            "--no-colors",
            "--progress-template",
            PROGRESS_TEMPLATE,
            "-o",
            output_template,
        ]

        # Only pass --ffmpeg-location when a real path is configured.
        # yt-dlp finds ffmpeg on PATH automatically; passing the bare name
        # "ffmpeg" to --ffmpeg-location actually breaks detection.
        if settings.ffmpeg_path and settings.ffmpeg_path not in ("ffmpeg", ""):
            args += ["--ffmpeg-location", settings.ffmpeg_path]

        fmt = job.format_id
        if fmt == "bestaudio":
            args += [
                "-f",
                "bestaudio/best",
                "-x",
                "--audio-format",
                settings.audio_format,
            ]
        elif fmt and fmt != "bestvideo":
            args += ["-f", fmt]
        else:
            # default / bestvideo -> best merged video+audio
            args += ["-f", "bestvideo*+bestaudio/best"]

        args.append(job.url)
        return args

    async def _worker(self) -> None:
        while self._running:
            try:
                job = await self._queue.get()
            except asyncio.CancelledError:
                break

            cancel_event = self._cancel_events.get(job.id)
            if cancel_event and cancel_event.is_set():
                self._queue.task_done()
                continue

            try:
                await self._run_job(job)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Job %s failed", job.id)
                job.status = "failed"
                job.error = str(exc)
                job.updated_at = datetime.utcnow()
                await self._persist_job(job)
                await self._broadcast(job)
            finally:
                self._queue.task_done()

    async def _run_job(self, job: Job) -> None:
        settings = await self._get_settings()
        os.makedirs(settings.download_folder, exist_ok=True)

        # fetch lightweight metadata for title/thumbnail (best effort)
        await self._enrich_metadata(job, settings)

        job.status = "downloading"
        job.updated_at = datetime.utcnow()
        await self._persist_job(job)
        await self._broadcast(job)

        args = self._build_args(job, settings)
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self._processes[job.id] = proc
        cancel_event = self._cancel_events.get(job.id)

        last_dest: Optional[str] = None
        assert proc.stdout is not None
        while True:
            if cancel_event and cancel_event.is_set():
                try:
                    proc.terminate()
                except ProcessLookupError:
                    pass
                break

            line_bytes = await proc.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode(errors="replace").rstrip()

            m = PROGRESS_RE.match(line)
            if m:
                status, percent, speed, eta = m.groups()
                job.progress = float(percent)
                job.speed = speed if speed not in ("NA", "Unknown") else None
                job.eta = eta if eta not in ("NA", "Unknown") else None
                job.updated_at = datetime.utcnow()
                await self._broadcast(job)
                continue

            dest = DEST_RE.search(line)
            if dest:
                last_dest = dest.group(1).strip()

        returncode = await proc.wait()
        self._processes.pop(job.id, None)

        if cancel_event and cancel_event.is_set():
            job.status = "cancelled"
            job.updated_at = datetime.utcnow()
            await self._persist_job(job)
            await self._broadcast(job)
            return

        if returncode == 0:
            job.status = "finished"
            job.progress = 100.0
            job.speed = None
            job.eta = None
            if last_dest:
                job.file_path = last_dest
            job.updated_at = datetime.utcnow()
            await self._persist_job(job)
            await self._write_history(job)
            await self._broadcast(job)
        else:
            job.status = "failed"
            job.error = f"yt-dlp exited with code {returncode}"
            job.updated_at = datetime.utcnow()
            await self._persist_job(job)
            await self._broadcast(job)

    async def _enrich_metadata(self, job: Job, settings: SettingsModel) -> None:
        try:
            args = [
                settings.ytdlp_path,
                "--dump-single-json",
                "--no-playlist",
                "--no-warnings",
                job.url,
            ]
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                data = json.loads(stdout.decode(errors="replace"))
                job.title = data.get("title")
                job.thumbnail = data.get("thumbnail")
        except Exception:  # noqa: BLE001
            logger.debug("metadata enrichment failed for %s", job.id)


# global singleton
manager = DownloadManager()
