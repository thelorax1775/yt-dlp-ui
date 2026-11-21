import asyncio
import json
import logging
import os
import re
import uuid
from collections import deque
from typing import AsyncGenerator, Optional

from sqlalchemy import select

from models.database import (
    AsyncSessionLocal,
    HistoryModel,
    JobModel,
    SettingsModel,
    utcnow,
)
from models.schemas import DownloadRequest, JobResponse
from services import metadata as lookup
from services.cookies import resolve_cookies_args

logger = logging.getLogger(__name__)

INTERRUPTED_MESSAGE = "interrupted by restart"

# Compact one-line progress template emitted by yt-dlp per tick.
PROGRESS_TEMPLATE = (
    "PROGRESS %(progress.status)s %(progress._percent_str)s "
    "%(progress._speed_str)s %(progress._eta_str)s"
)

PROGRESS_RE = re.compile(
    r"^PROGRESS\s+(\S+)\s+(N/A|[\d.]+)%\s+(.+?)\s+(\S+)\s*$"
)

# yt-dlp prints the final merged/destination path with these markers.
DEST_RE = re.compile(r"\[(?:download|Merger|ExtractAudio)\].*?(?:Destination:|to|into)\s+\"?(.+?)\"?$")

# Emitted by our `--print after_move:...` flag once the final file is in place;
# more reliable than DEST_RE, which stays as a fallback for older yt-dlp.
FILEPATH_PRINT_TEMPLATE = "after_move:OUTPATH %(filepath)s"
FILEPATH_RE = re.compile(r"^OUTPATH (.+)$")


def _is_audio_only(job: "Job") -> bool:
    """True when the job extracts audio rather than keeping the video."""
    return job.format_id == "bestaudio"


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
        self.created_at = utcnow()
        self.updated_at = utcnow()
        # Bumped on every retry. A queue entry only runs while it carries the
        # job's current attempt, so a stale entry can never start a second run.
        self.attempt = 0

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
        self._queue: asyncio.Queue[tuple[Job, int]] = asyncio.Queue()
        self._jobs: dict[str, Job] = {}
        self._subscribers: list[asyncio.Queue] = []
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._workers: list[asyncio.Task] = []
        self._persist_tasks: set[asyncio.Task] = set()
        self._running = False

    # ---------- lifecycle ----------

    async def start(self) -> None:
        self._running = True
        await self._load_jobs()
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
        workers = list(self._workers)
        self._workers.clear()
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        # Database writes started by a cancelled worker finish before we return,
        # so no connection is left half-closed.
        if self._persist_tasks:
            await asyncio.gather(*list(self._persist_tasks), return_exceptions=True)

    async def _load_jobs(self) -> None:
        """Read the jobs table back. Nothing is restarted automatically.

        Jobs that were queued or downloading when the last process died are
        marked failed ("interrupted by restart") so they can be retried.
        """
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(select(JobModel))).scalars().all()
            for row in rows:
                job = Job(url=row.url, format_id=row.format_id)
                job.id = row.id
                job.title = row.title
                job.thumbnail = row.thumbnail
                job.status = row.status
                job.progress = row.progress or 0.0
                job.speed = row.speed
                job.eta = row.eta
                job.file_path = row.file_path
                job.error = row.error
                job.created_at = row.created_at or job.created_at
                job.updated_at = row.updated_at or job.updated_at
                if job.status in ("queued", "downloading"):
                    job.status = "failed"
                    job.error = INTERRUPTED_MESSAGE
                    job.speed = None
                    job.eta = None
                    job.updated_at = utcnow()
                    row.status = job.status
                    row.error = job.error
                    row.speed = None
                    row.eta = None
                    row.updated_at = job.updated_at
                self._jobs[job.id] = job
                self._cancel_events[job.id] = asyncio.Event()
            await session.commit()

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
        await self._queue.put((job, job.attempt))
        await self._broadcast(job)
        return job

    async def retry(self, job_id: str) -> Optional[Job]:
        old = self._jobs.get(job_id)
        if not old or old.status not in ("failed", "cancelled"):
            return None
        old.attempt += 1
        old.status = "queued"
        old.progress = 0.0
        old.speed = None
        old.eta = None
        old.error = None
        old.updated_at = utcnow()
        self._cancel_events[job_id] = asyncio.Event()
        await self._persist_job(old)
        await self._queue.put((old, old.attempt))
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
            job.updated_at = utcnow()
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
            # send current snapshot immediately (copy: q.put awaits, and a
            # concurrent enqueue() would mutate the dict mid-iteration)
            for job in list(self._jobs.values()):
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
        """Write the job row; cancelling the caller cannot cut the write off."""
        task = asyncio.ensure_future(self._persist_job_now(job))
        self._persist_tasks.add(task)
        task.add_done_callback(self._persist_tasks.discard)
        await asyncio.shield(task)

    async def _persist_job_now(self, job: Job) -> None:
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
            await session.merge(
                HistoryModel(
                    id=job.id,
                    url=job.url,
                    title=job.title,
                    thumbnail=job.thumbnail,
                    file_path=job.file_path,
                    format_id=job.format_id,
                    finished_at=utcnow(),
                )
            )
            await session.commit()

    def _target_folder(self, job: Job, settings: SettingsModel) -> str:
        """Audio-only jobs land in the audio folder when one is configured."""
        if _is_audio_only(job) and settings.audio_download_folder:
            return settings.audio_download_folder
        return settings.download_folder

    def _build_args(self, job: Job, settings: SettingsModel) -> list[str]:
        folder = self._target_folder(job, settings)
        # Escape any "%" in the folder so yt-dlp doesn't treat it as a template.
        safe_folder = folder.replace("%", "%%")
        output_template = os.path.join(safe_folder, "%(title)s.%(ext)s")
        args = [
            settings.ytdlp_path,
            "--no-playlist",
            "--newline",
            "--no-colors",
            # --print implies --quiet, so force progress back on to keep the
            # progress-template lines flowing.
            "--progress",
            "--progress-template",
            PROGRESS_TEMPLATE,
            "--print",
            FILEPATH_PRINT_TEMPLATE,
            "-o",
            output_template,
        ]
        args += resolve_cookies_args(settings)

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
                # Untagged audio shows up in a music library as "Unknown
                # Artist", so write what YouTube knows into the file, and
                # fall back to the uploader when it reports no artist.
                "--embed-metadata",
                "--parse-metadata",
                "%(artist,uploader|)s:%(meta_artist)s",
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
                job, attempt = await self._queue.get()
            except asyncio.CancelledError:
                break

            # Skip entries left behind by a cancel or a retry: a job runs once
            # per attempt, and only while it is still waiting in the queue.
            cancel_event = self._cancel_events.get(job.id)
            if (
                attempt != job.attempt
                or job.status != "queued"
                or cancel_event is None
                or cancel_event.is_set()
            ):
                self._queue.task_done()
                continue

            try:
                await self._run_job(job, attempt, cancel_event)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Job %s failed", job.id)
                if attempt != job.attempt:
                    continue
                job.status = "failed"
                job.error = str(exc)
                job.updated_at = utcnow()
                await self._persist_job(job)
                await self._broadcast(job)
            finally:
                self._queue.task_done()

    async def _run_job(self, job: Job, attempt: int, cancel_event: asyncio.Event) -> None:
        settings = await self._get_settings()
        os.makedirs(self._target_folder(job, settings), exist_ok=True)

        # fetch lightweight metadata for title/thumbnail (best effort, but a
        # lookup that hangs fails the job, and cancel kills it)
        try:
            await self._enrich_metadata(job, settings, cancel_event)
        except lookup.LookupCancelled:
            return  # cancel() already recorded the cancelled state
        if cancel_event.is_set() or attempt != job.attempt:
            return

        job.status = "downloading"
        job.updated_at = utcnow()
        await self._persist_job(job)
        await self._broadcast(job)

        args = self._build_args(job, settings)
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self._processes[job.id] = proc

        last_dest: Optional[str] = None
        final_path: Optional[str] = None
        error_lines: list[str] = []
        tail: deque[str] = deque(maxlen=8)
        assert proc.stdout is not None
        while True:
            if cancel_event.is_set():
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
                if percent != "N/A":
                    job.progress = float(percent)
                speed = speed.strip()
                job.speed = (
                    None if speed in ("NA", "N/A", "Unknown", "Unknown B/s") else speed
                )
                job.eta = eta if eta not in ("NA", "Unknown") else None
                job.updated_at = utcnow()
                await self._broadcast(job)
                continue

            # Progress ticks are not output worth surfacing as an error later.
            if line.startswith("PROGRESS"):
                continue

            if line.strip():
                tail.append(line.strip())
            if line.startswith("ERROR") and len(error_lines) < 5:
                error_lines.append(line.strip())

            printed = FILEPATH_RE.match(line)
            if printed:
                final_path = printed.group(1).strip()
                continue

            dest = DEST_RE.search(line)
            if dest:
                last_dest = dest.group(1).strip()

        returncode = await proc.wait()
        if self._processes.get(job.id) is proc:
            del self._processes[job.id]

        if attempt != job.attempt:
            return

        if cancel_event.is_set():
            job.status = "cancelled"
            job.updated_at = utcnow()
            await self._persist_job(job)
            await self._broadcast(job)
            return

        if returncode == 0:
            job.status = "finished"
            job.progress = 100.0
            job.speed = None
            job.eta = None
            if final_path or last_dest:
                job.file_path = final_path or last_dest
            job.updated_at = utcnow()
            await self._persist_job(job)
            await self._write_history(job)
            await self._broadcast(job)
        else:
            job.status = "failed"
            if error_lines:
                job.error = "\n".join(error_lines)
            elif tail:
                job.error = "\n".join(tail)
            else:
                job.error = f"yt-dlp exited with code {returncode}"
            job.updated_at = utcnow()
            await self._persist_job(job)
            await self._broadcast(job)

    async def _enrich_metadata(
        self, job: Job, settings: SettingsModel, cancel_event: asyncio.Event
    ) -> None:
        args = [
            settings.ytdlp_path,
            "--dump-single-json",
            "--no-playlist",
            "--no-warnings",
            *resolve_cookies_args(settings),
            job.url,
        ]

        current: dict = {}

        def remember(proc) -> None:
            current["proc"] = proc
            self._processes[job.id] = proc

        try:
            returncode, stdout, _ = await lookup.run_lookup(args, cancel_event, remember)
            if returncode == 0:
                data = json.loads(stdout.decode(errors="replace"))
                job.title = data.get("title")
                job.thumbnail = data.get("thumbnail")
        except (lookup.LookupCancelled, lookup.LookupTimeout):
            raise
        except Exception:  # noqa: BLE001
            logger.debug("metadata enrichment failed for %s", job.id)
        finally:
            if self._processes.get(job.id) is current.get("proc"):
                self._processes.pop(job.id, None)


# global singleton
manager = DownloadManager()
