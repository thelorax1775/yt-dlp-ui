import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import downloads, files, history, info, search, settings, shares
from models.database import init_db, seed_settings
from services.cookies import ensure_cookies_file
from services.download_manager import manager
from services.share_manager import auto_mount_all

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await seed_settings()
    await ensure_cookies_file()
    await auto_mount_all()
    await manager.start()
    yield
    await manager.stop()


app = FastAPI(title="yt-dlp Web UI", version="0.1.0", lifespan=lifespan)


def cors_origins(raw: str | None) -> list[str]:
    """Origins from CORS_ORIGINS (comma separated). Empty means none.

    A bare "*" is ignored: the API has no login, so letting every website
    read its answers would hand the whole app to any page the user opens.
    """
    origins: list[str] = []
    for item in (raw or "").split(","):
        origin = item.strip().rstrip("/")
        if not origin:
            continue
        if origin == "*":
            logger.warning("CORS_ORIGINS: ignoring '*'; list the exact origins instead")
            continue
        origins.append(origin)
    return origins


# The bundled frontend calls the API through its own /api proxy (same origin),
# so by default no other website is allowed to read API responses. Extra
# origins are an explicit allow-list. Credentials stay disabled.
_cors_origins = cors_origins(os.environ.get("CORS_ORIGINS"))
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(info.router, prefix="/api", tags=["info"])
app.include_router(downloads.router, prefix="/api", tags=["downloads"])
app.include_router(history.router, prefix="/api", tags=["history"])
app.include_router(settings.router, prefix="/api", tags=["settings"])
app.include_router(shares.router, prefix="/api", tags=["shares"])
app.include_router(files.router, prefix="/api", tags=["files"])
app.include_router(search.router, prefix="/api", tags=["search"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}
