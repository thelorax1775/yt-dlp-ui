import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import downloads, history, info, settings
from models.database import init_db, seed_settings
from services.download_manager import manager

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await seed_settings()
    await manager.start()
    yield
    await manager.stop()


app = FastAPI(title="yt-dlp Web UI", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(info.router, prefix="/api", tags=["info"])
app.include_router(downloads.router, prefix="/api", tags=["downloads"])
app.include_router(history.router, prefix="/api", tags=["history"])
app.include_router(settings.router, prefix="/api", tags=["settings"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}
