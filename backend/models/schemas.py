from datetime import datetime
from typing import Optional
from pydantic import BaseModel, HttpUrl, field_validator


class FormatInfo(BaseModel):
    format_id: str
    ext: str
    resolution: Optional[str] = None
    fps: Optional[float] = None
    vcodec: Optional[str] = None
    acodec: Optional[str] = None
    filesize: Optional[int] = None
    format_note: Optional[str] = None


class MetadataResponse(BaseModel):
    title: str
    thumbnail: Optional[str] = None
    uploader: Optional[str] = None
    duration: Optional[int] = None
    url: str
    formats: list[FormatInfo] = []


class DownloadRequest(BaseModel):
    url: str
    format_id: Optional[str] = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class JobResponse(BaseModel):
    id: str
    url: str
    title: Optional[str] = None
    thumbnail: Optional[str] = None
    status: str
    format_id: Optional[str] = None
    progress: float = 0.0
    speed: Optional[str] = None
    eta: Optional[str] = None
    file_path: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class HistoryEntry(BaseModel):
    id: str
    url: Optional[str] = None
    title: Optional[str] = None
    thumbnail: Optional[str] = None
    file_path: Optional[str] = None
    format_id: Optional[str] = None
    finished_at: Optional[datetime] = None


class SettingsResponse(BaseModel):
    download_folder: str
    audio_format: str
    concurrent_downloads: int
    ytdlp_path: str
    ffmpeg_path: str


class SettingsUpdate(BaseModel):
    download_folder: Optional[str] = None
    audio_format: Optional[str] = None
    concurrent_downloads: Optional[int] = None
    ytdlp_path: Optional[str] = None
    ffmpeg_path: Optional[str] = None
