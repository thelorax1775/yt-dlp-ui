from datetime import datetime
from typing import Optional
from pydantic import BaseModel, HttpUrl, field_validator


class FormatInfo(BaseModel):
    format_id: str
    ext: str
    resolution: Optional[str] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    vcodec: Optional[str] = None
    acodec: Optional[str] = None
    filesize: Optional[int] = None
    format_note: Optional[str] = None


class ResolutionOption(BaseModel):
    height: int
    label: str  # e.g. "1080p"
    ext: Optional[str] = None
    filesize: Optional[int] = None


class MetadataResponse(BaseModel):
    title: str
    thumbnail: Optional[str] = None
    uploader: Optional[str] = None
    duration: Optional[int] = None
    url: str
    formats: list[FormatInfo] = []
    resolutions: list[ResolutionOption] = []


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


class ShareBase(BaseModel):
    name: str
    type: str  # "smb" | "nfs"
    remote: str
    mount_point: str
    username: Optional[str] = None
    password: Optional[str] = None
    domain: Optional[str] = None
    options: Optional[str] = None
    auto_mount: bool = False

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("smb", "nfs"):
            raise ValueError("type must be 'smb' or 'nfs'")
        return v


class ShareCreate(ShareBase):
    pass


class ShareResponse(BaseModel):
    id: int
    name: str
    type: str
    remote: str
    mount_point: str
    username: Optional[str] = None
    domain: Optional[str] = None
    options: Optional[str] = None
    auto_mount: bool = False
    mounted: bool = False
    # password intentionally omitted from responses


class MountResult(BaseModel):
    mounted: bool
    message: Optional[str] = None


class FileEntry(BaseModel):
    name: str
    path: str  # path relative to the download root
    is_dir: bool
    size: Optional[int] = None
    modified: Optional[datetime] = None


class FileListResponse(BaseModel):
    root: str  # absolute download root
    path: str  # current path relative to root ("" = root)
    entries: list[FileEntry] = []


class RenameRequest(BaseModel):
    path: str  # existing path relative to root
    new_name: str  # new base name (no slashes)

    @field_validator("new_name")
    @classmethod
    def validate_new_name(cls, v: str) -> str:
        v = v.strip()
        if not v or "/" in v or "\\" in v or v in (".", ".."):
            raise ValueError("Invalid file name")
        return v


class MkdirRequest(BaseModel):
    path: str  # parent path relative to root
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v or "/" in v or "\\" in v or v in (".", ".."):
            raise ValueError("Invalid folder name")
        return v
