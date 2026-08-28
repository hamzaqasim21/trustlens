"""HTTP surface.

Everything is under /api/v1 so the Trust Score Engine, the React dashboard, the
Flutter app and the extension all talk to one stable contract.

Endpoints:
  POST /api/v1/transcribe/url      - an Instagram (or TikTok) link
  POST /api/v1/transcribe/upload   - a file
  POST /api/v1/transcribe/direct   - a CDN URL captured by the extension
  POST /api/v1/transcribe/raw      - synchronous ASR on prepared audio; this is
                                     what a remote GPU worker exposes
  GET  /api/v1/jobs/{id}           - poll
  GET  /api/v1/jobs/{id}/stream    - server-sent progress events
  GET  /api/v1/jobs                - recent jobs
  GET  /api/v1/health              - readiness + capability report
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app import __version__
from app.config import settings
from app.db import purge_old_jobs, stats as db_stats
from app.jobs import manager
from app.pipeline import acquire, asr, ocr
from app.pipeline.ffmpeg_tools import FFmpegError, ffmpeg_path
from app.pipeline.orchestrator import TranscriptionRequest
from app.schemas import (
    HealthResponse, JobSubmitted, TranscribeDirectRequest, TranscribeUrlRequest,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")

_ALLOWED_UPLOAD_SUFFIXES = {
    ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".3gp", ".flv", ".ts",
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wma",
}


def _submitted(job_id: str, cache_hit: bool, request: Request) -> JobSubmitted:
    base = str(request.base_url).rstrip("/")
    return JobSubmitted(
        job_id=job_id,
        status="completed" if cache_hit else "queued",
        cache_hit=cache_hit,
        poll_url=f"{base}/api/v1/jobs/{job_id}",
        stream_url=f"{base}/api/v1/jobs/{job_id}/stream",
        message=("Served from cache." if cache_hit else
                 f"Queued. {manager.queue_depth} job(s) ahead."),
    )


async def _maybe_wait(job_id: str, wait: bool, timeout: float = 1800.0) -> dict | None:
    """Block until the job settles, for callers that prefer one round trip."""
    if not wait:
        return None
    waited = 0.0
    step = 0.4
    while waited < timeout:
        state = manager.get(job_id)
        if state and state["status"] in ("completed", "failed"):
            return state
        await asyncio.sleep(step)
        waited += step
        step = min(step * 1.15, 2.5)
    raise HTTPException(504, f"Job {job_id} did not finish within {timeout:.0f}s.")


# --------------------------------------------------------------------------- #
# URL
# --------------------------------------------------------------------------- #
@router.post("/transcribe/url", summary="Transcribe from a public link")
async def transcribe_url(payload: TranscribeUrlRequest, request: Request):
    if not acquire.is_supported_url(payload.url):
        log.info("Unrecognised host, attempting anyway: %s", payload.url[:120])

    req = TranscriptionRequest(
        url=payload.url,
        language=payload.language,
        task=payload.task,
        model=payload.model,
        force_ocr=payload.force_ocr,
        denoise=payload.denoise,
    )
    job_id, cached = await manager.submit(req)

    final = await _maybe_wait(job_id, payload.wait)
    if final is not None:
        if final["status"] == "failed":
            raise HTTPException(422, final.get("error") or "Transcription failed.")
        return final
    return _submitted(job_id, cached, request)


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #
@router.post("/transcribe/upload", summary="Transcribe an uploaded file")
async def transcribe_upload(
    request: Request,
    file: UploadFile = File(...),
    language: str | None = Form(None),
    task: str = Form("transcribe"),
    model: str | None = Form(None),
    force_ocr: bool = Form(False),
    denoise: str | None = Form(None),
    wait: bool = Form(False),
):
    original = Path(file.filename or "upload.bin").name
    suffix = Path(original).suffix.lower()
    if suffix and suffix not in _ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(
            415,
            f"Unsupported file type {suffix!r}. Accepted: "
            f"{', '.join(sorted(_ALLOWED_UPLOAD_SUFFIXES))}",
        )

    workdir = settings.media_dir / f"upload_{uuid.uuid4().hex[:16]}"
    workdir.mkdir(parents=True, exist_ok=True)
    target = workdir / f"source{suffix or '.bin'}"
    limit = settings.max_upload_mb * 1024 * 1024
    written = 0

    try:
        async with aiofiles.open(target, "wb") as fh:
            while chunk := await file.read(1 << 20):
                written += len(chunk)
                if written > limit:
                    raise HTTPException(
                        413, f"File exceeds the {settings.max_upload_mb} MB limit."
                    )
                await fh.write(chunk)
    except HTTPException:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(500, f"Could not save the upload: {exc}") from exc
    finally:
        await file.close()

    if written == 0:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(400, "The uploaded file is empty.")

    req = TranscriptionRequest(
        upload_path=target,
        upload_name=original,
        language=(language or None),
        task=task if task in ("transcribe", "translate") else "transcribe",
        model=(model or None),
        force_ocr=force_ocr,
        denoise=(denoise or None),
    )
    job_id, cached = await manager.submit(req)

    final = await _maybe_wait(job_id, wait)
    if final is not None:
        if final["status"] == "failed":
            raise HTTPException(422, final.get("error") or "Transcription failed.")
        return final
    return _submitted(job_id, cached, request)


# --------------------------------------------------------------------------- #
# Direct CDN (browser extension)
# --------------------------------------------------------------------------- #
@router.post("/transcribe/direct", summary="Transcribe a CDN URL captured by the extension")
async def transcribe_direct(payload: TranscribeDirectRequest, request: Request):
    req = TranscriptionRequest(
        direct_url=payload.media_url,
        direct_headers=payload.headers,
        source_page=payload.page_url,
        language=payload.language,
        task=payload.task,
        force_ocr=payload.force_ocr,
    )
    job_id, cached = await manager.submit(req)

    final = await _maybe_wait(job_id, payload.wait)
    if final is not None:
        if final["status"] == "failed":
            raise HTTPException(422, final.get("error") or "Transcription failed.")
        return final
    return _submitted(job_id, cached, request)


# --------------------------------------------------------------------------- #
# Raw synchronous ASR - the remote-GPU worker contract
# --------------------------------------------------------------------------- #
@router.post("/transcribe/raw", summary="Synchronous ASR on prepared audio (worker API)")
async def transcribe_raw(
    file: UploadFile = File(...),
    language: str | None = Form(None),
    task: str = Form("transcribe"),
):
    """Bypasses the queue and the acquisition stage.

    This exists so an instance of this service running on a free Colab/Kaggle GPU
    can act as the ASR backend for a laptop instance. Set ASR_BACKEND=remote and
    REMOTE_ASR_URL on the laptop and it calls this.
    """
    workdir = settings.media_dir / f"raw_{uuid.uuid4().hex[:12]}"
    workdir.mkdir(parents=True, exist_ok=True)
    target = workdir / (Path(file.filename or "audio.wav").name)
    try:
        async with aiofiles.open(target, "wb") as fh:
            while chunk := await file.read(1 << 20):
                await fh.write(chunk)
        await file.close()

        result = await asyncio.to_thread(
            asr.transcribe,
            target,
            language=(language or None),
            task=task if task in ("transcribe", "translate") else "transcribe",
        )
        return {
            "segments": result.segments,
            "language": result.language,
            "language_probability": result.language_probability,
            "language_decision": result.language_decision,
            "duration": result.duration,
            "duration_after_vad": result.duration_after_vad,
            "model": result.model,
            "device": result.device,
            "compute_type": result.compute_type,
            "realtime_factor": result.realtime_factor,
        }
    except asr.ASRError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
@router.get("/jobs/{job_id}", summary="Poll a job")
async def get_job(job_id: str):
    state = manager.get(job_id)
    if state is None:
        raise HTTPException(404, f"No job with id {job_id}.")
    return state


@router.get("/jobs", summary="List recent jobs")
async def list_jobs(limit: int = 50, status: str | None = None):
    if status and status not in ("queued", "running", "completed", "failed"):
        raise HTTPException(400, "status must be queued, running, completed or failed.")
    return {"jobs": manager.list_recent(limit=limit, status=status)}


@router.get("/jobs/{job_id}/stream", summary="Live progress (server-sent events)")
async def stream_job(job_id: str, request: Request):
    state = manager.get(job_id)
    if state is None:
        raise HTTPException(404, f"No job with id {job_id}.")

    async def events():
        # Replay current state first so a late subscriber is not left blank.
        yield f"data: {json.dumps(state, ensure_ascii=False)}\n\n"
        if state["status"] in ("completed", "failed"):
            yield "event: end\ndata: {}\n\n"
            return

        q = manager.subscribe(job_id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"        # stops proxies closing the stream
                    continue

                if payload.get("_eof"):
                    final = manager.get(job_id)
                    if final:
                        yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
                    yield "event: end\ndata: {}\n\n"
                    break
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            manager.unsubscribe(job_id, q)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --------------------------------------------------------------------------- #
# Ops
# --------------------------------------------------------------------------- #
@router.get("/health", response_model=HealthResponse, summary="Readiness and capabilities")
async def health():
    device, compute = settings.resolve_device()
    try:
        ff = {"available": True, "path": ffmpeg_path()}
    except FFmpegError as exc:
        ff = {"available": False, "error": str(exc)}

    try:
        db_info = {"url_scheme": settings.sqlalchemy_url.split(":", 1)[0], **db_stats()}
        db_ok = True
    except Exception as exc:
        db_info, db_ok = {"error": str(exc)}, False

    return HealthResponse(
        status="ok" if (ff["available"] and db_ok) else "degraded",
        app=settings.app_name,
        version=__version__,
        asr={
            "backend": settings.asr_backend,
            "model": settings.asr_model,
            "device": device,
            "compute_type": compute,
            "cpu_threads": settings.resolve_cpu_threads(),
            "loaded": asr.model_is_loaded(),
            "vad_enabled": settings.vad_enabled,
            "urdu_bias": settings.urdu_bias_enabled,
            "remote_url": settings.remote_asr_url or None,
        },
        ffmpeg=ff,
        ocr={
            "enabled": settings.ocr_enabled,
            "installed": ocr.is_available(),
            "languages": settings.ocr_language_list,
            "auto_fallback": settings.ocr_auto_fallback,
        },
        queue={"depth": manager.queue_depth, "workers": manager.workers},
        database=db_info,
    )


@router.post("/admin/warmup", summary="Preload the model")
async def warmup(model: str | None = None):
    try:
        return await asyncio.to_thread(asr.warm_up, model)
    except asr.ASRError as exc:
        raise HTTPException(500, str(exc)) from exc


@router.post("/admin/purge", summary="Delete jobs past the retention window")
async def purge():
    removed = await asyncio.to_thread(purge_old_jobs)
    return {"deleted": removed, "retention_hours": settings.job_retention_hours}
