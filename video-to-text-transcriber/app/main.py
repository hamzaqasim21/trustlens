"""FastAPI application entrypoint.

Run it:
    python run.py
    # or
    uvicorn app.main:app --reload
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.routes import router
from app.config import BASE_DIR, settings
from app.db import init_db
from app.jobs import manager
from app.pipeline.ffmpeg_tools import FFmpegError, ffmpeg_path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)-28s %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("trustlens.transcriber")

WEB_DIR = BASE_DIR / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=" * 68)
    log.info(" %s v%s", settings.app_name, __version__)
    log.info("=" * 68)

    init_db()
    log.info("Database ready: %s", settings.sqlalchemy_url.split("://", 1)[0])

    try:
        log.info("FFmpeg: %s", ffmpeg_path())
    except FFmpegError as exc:
        log.error("FFmpeg unavailable - audio extraction will fail. %s", exc)

    device, compute = settings.resolve_device()
    log.info(
        "ASR: %s backend | model=%s | %s/%s | %d threads",
        settings.asr_backend, settings.asr_model, device, compute,
        settings.resolve_cpu_threads(),
    )
    if device == "cpu" and settings.asr_model in ("large-v3", "large-v2", "large"):
        log.warning(
            "large-v3 on CPU is very slow (expect several minutes per clip). "
            "Use ASR_MODEL=small for local work, or point ASR_BACKEND=remote at a "
            "free GPU runner for full-accuracy runs."
        )
    if settings.ocr_enabled:
        from app.pipeline import ocr
        log.info("OCR: enabled (EasyOCR installed=%s)", ocr.is_available())

    await manager.start()
    log.info("Ready on http://%s:%d  (docs at /docs)", settings.host, settings.port)
    try:
        yield
    finally:
        await manager.stop()


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Module 12 of TrustLens. Extracts audio from Instagram Reels, TikToks and "
        "uploaded video, transcribes it with OpenAI Whisper (running on the "
        "CTranslate2 runtime), and returns classifier-ready Urdu or English text "
        "with a calibrated confidence score."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/", include_in_schema=False)
async def index():
    idx = WEB_DIR / "index.html"
    if idx.exists():
        return FileResponse(idx)
    return {
        "app": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "health": "/api/v1/health",
    }


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
