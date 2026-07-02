import os
from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_PATH = os.environ.get("DATABASE_PATH", "./ytdlp_ui.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_PATH}"

# Directory holding the DB file; managed data (e.g. cookies.txt) lives here
# so it persists alongside the database volume.
DATA_DIR = os.path.dirname(os.path.abspath(DATABASE_PATH))

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class SettingsModel(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, default=1)
    download_folder = Column(Text, nullable=False, default="/downloads")
    audio_format = Column(String(16), nullable=False, default="mp3")
    concurrent_downloads = Column(Integer, nullable=False, default=2)
    ytdlp_path = Column(Text, nullable=False, default="yt-dlp")
    ffmpeg_path = Column(Text, nullable=False, default="ffmpeg")
    # Pasted Netscape-format cookies.txt content (source of record; a copy is
    # materialized to a file for yt-dlp, which rotates cookies in that file).
    cookies_content = Column(Text, nullable=True)
    # Optional explicit cookies file path (e.g. mounted into the container);
    # takes precedence over the managed file when set.
    cookies_file_path = Column(Text, nullable=True)


class JobModel(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True)
    url = Column(Text, nullable=False)
    title = Column(Text)
    thumbnail = Column(Text)
    status = Column(String(16), nullable=False, default="queued")
    format_id = Column(Text)
    progress = Column(Float, default=0.0)
    speed = Column(Text)
    eta = Column(Text)
    file_path = Column(Text)
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class HistoryModel(Base):
    __tablename__ = "history"

    id = Column(String(36), primary_key=True)
    url = Column(Text)
    title = Column(Text)
    thumbnail = Column(Text)
    file_path = Column(Text)
    format_id = Column(Text)
    finished_at = Column(DateTime, default=datetime.utcnow)


class ShareModel(Base):
    __tablename__ = "shares"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    type = Column(String(8), nullable=False)  # "smb" | "nfs"
    remote = Column(Text, nullable=False)  # //host/share  or  host:/export
    mount_point = Column(Text, nullable=False)
    username = Column(Text)  # smb only
    password = Column(Text)  # smb only
    domain = Column(Text)  # smb only
    options = Column(Text)  # extra mount options (comma separated)
    auto_mount = Column(Integer, nullable=False, default=0)  # bool (0/1)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_settings_columns(conn)


async def _migrate_settings_columns(conn) -> None:
    # create_all never adds columns to an existing table, so add any
    # settings columns introduced after the table was first created.
    result = await conn.exec_driver_sql("PRAGMA table_info(settings)")
    existing = {row[1] for row in result.fetchall()}
    for column in ("cookies_content", "cookies_file_path"):
        if column not in existing:
            await conn.exec_driver_sql(
                f"ALTER TABLE settings ADD COLUMN {column} TEXT"
            )


async def seed_settings() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.get(SettingsModel, 1)
        if result is None:
            session.add(SettingsModel(id=1))
            await session.commit()


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
