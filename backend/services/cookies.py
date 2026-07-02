import logging
import os

from models.database import DATA_DIR, AsyncSessionLocal, SettingsModel

logger = logging.getLogger(__name__)

# Managed cookies file, materialized from settings.cookies_content. It is only
# (re)written when the user saves new cookies or when it is missing at startup:
# yt-dlp rotates cookies and writes them back into this file, and overwriting
# it from the stored copy on every run would invalidate the rotated session.
COOKIES_PATH = os.path.join(DATA_DIR, "cookies.txt")


def validate_cookies_content(content: str) -> bool:
    """Accept anything that plausibly is Netscape cookies.txt format."""
    stripped = content.strip()
    if stripped.startswith("# Netscape") or stripped.startswith("# HTTP Cookie File"):
        return True
    return any(
        len(line.split("\t")) >= 7
        for line in stripped.splitlines()
        if line and not line.startswith("#")
    )


def write_cookies_file(content: str) -> None:
    fd = os.open(COOKIES_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(content)
    os.chmod(COOKIES_PATH, 0o600)


def clear_cookies_file() -> None:
    try:
        os.remove(COOKIES_PATH)
    except FileNotFoundError:
        pass


def resolve_cookies_args(settings: SettingsModel | None) -> list[str]:
    """Extra yt-dlp args enabling cookie auth, or [] when not configured."""
    if settings is not None:
        explicit = (settings.cookies_file_path or "").strip()
        if explicit:
            return ["--cookies", explicit]
    if os.path.isfile(COOKIES_PATH) and os.path.getsize(COOKIES_PATH) > 0:
        return ["--cookies", COOKIES_PATH]
    return []


async def ensure_cookies_file() -> None:
    """Re-materialize the managed cookies file from the DB if it is missing."""
    if os.path.exists(COOKIES_PATH):
        return
    async with AsyncSessionLocal() as session:
        settings = await session.get(SettingsModel, 1)
        if settings and settings.cookies_content:
            write_cookies_file(settings.cookies_content)
            logger.info("Restored cookies file at %s", COOKIES_PATH)
