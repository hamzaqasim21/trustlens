"""Async job queue.

The scope document calls for asynchronous background workers, and it is not
optional here: on a CPU-only machine a 30-second reel takes tens of seconds to
transcribe, which is far too long to hold an HTTP request open. So the API
accepts work, returns a job id immediately, and the caller polls or subscribes.

Deliberately *not* Celery + Redis. That is the textbook answer, but it means
running a broker and a separate worker process for a workload that is a handful
of jobs at a time on one machine. An asyncio queue plus a bounded thread pool
does the same job here with no extra infrastructure to install or explain. The
`submit` / `get` / `subscribe` surface is small enough that dropping Celery in
behind it later is a contained change.

Concurrency is 1 by default and that is on purpose: Whisper already saturates
every core it is given, so running two jobs at once on a 2-core laptop makes
both slower than running them in sequence.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.config import settings
from app.db import TranscriptionJob, find_cached, session_scope, utcnow
from app.pipeline.orchestrator import (
    PipelineError, TranscriptionRequest, content_fingerprint, run_pipeline,
)

log = logging.getLogger(__name__)


class JobManager:
    def __init__(self, workers: int | None = None) -> None:
        self.workers = max(1, workers if workers is not None else settings.job_workers)
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._tasks: list[asyncio.Task] = []
        self._pool = ThreadPoolExecutor(
            max_workers=self.workers, thread_name_prefix="asr-worker"
        )
        self._pending: dict[str, TranscriptionRequest] = {}
        self._listeners: dict[str, set[asyncio.Queue]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running = False

    # ----------------------------------------------------------------- #
    # lifecycle
    # ----------------------------------------------------------------- #
    async def start(self) -> None:
        if self._running:
            return
        self._loop = asyncio.get_running_loop()
        self._running = True
        for i in range(self.workers):
            self._tasks.append(asyncio.create_task(self._worker(i), name=f"asr-worker-{i}"))
        log.info("Job manager started with %d worker(s).", self.workers)

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks.clear()
        self._pool.shutdown(wait=False, cancel_futures=True)
        log.info("Job manager stopped.")

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    # ----------------------------------------------------------------- #
    # submission
    # ----------------------------------------------------------------- #
    async def submit(self, req: TranscriptionRequest) -> tuple[str, bool]:
        """Queue a job. Returns (job_id, was_cache_hit)."""
        job_id = uuid.uuid4().hex[:16]
        fingerprint = await asyncio.to_thread(content_fingerprint, req)

        cached = await asyncio.to_thread(find_cached, fingerprint) if settings.cache_enabled else None
        if cached and cached.result:
            with session_scope() as s:
                row = TranscriptionJob(
                    id=job_id,
                    fingerprint=fingerprint,
                    status="completed",
                    progress=1.0,
                    stage="served from cache",
                    source_kind=cached.source_kind,
                    source_ref=cached.source_ref,
                    platform=cached.platform,
                    requested_language=req.language or "",
                    task=req.task,
                    model=req.model or settings.asr_model,
                    detected_language=cached.detected_language,
                    transcript_text=cached.transcript_text,
                    confidence=cached.confidence,
                    quality=cached.quality,
                    result=cached.result,
                    started_at=utcnow(),
                    finished_at=utcnow(),
                    duration_seconds=0.0,
                    cache_hit=1,
                )
                s.add(row)
            log.info("Job %s served from cache.", job_id)
            return job_id, True

        with session_scope() as s:
            s.add(TranscriptionJob(
                id=job_id,
                fingerprint=fingerprint,
                status="queued",
                progress=0.0,
                stage="queued",
                source_kind=("upload" if req.upload_path else
                             "direct" if req.direct_url else "url"),
                source_ref=(req.upload_name or req.direct_url or req.url or "")[:2000],
                platform="",
                requested_language=req.language or "",
                task=req.task,
                model=req.model or settings.asr_model,
            ))

        self._pending[job_id] = req
        await self._queue.put(job_id)
        return job_id, False

    # ----------------------------------------------------------------- #
    # worker
    # ----------------------------------------------------------------- #
    async def _worker(self, idx: int) -> None:
        while self._running:
            try:
                job_id = await self._queue.get()
            except asyncio.CancelledError:
                return

            req = self._pending.pop(job_id, None)
            if req is None:
                self._queue.task_done()
                continue

            log.info("[worker %d] starting job %s", idx, job_id)
            self._update(job_id, status="running", stage="starting", progress=0.01,
                         started_at=utcnow())
            await self._publish(job_id, {"status": "running", "progress": 0.01,
                                         "stage": "starting"})
            t0 = datetime.now(timezone.utc)

            try:
                out = await asyncio.get_running_loop().run_in_executor(
                    self._pool, self._run_sync, job_id, req
                )
                elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
                d = out.as_dict()
                self._update(
                    job_id,
                    status="completed", progress=1.0, stage="done",
                    result=d,
                    transcript_text=d["transcript"]["text"],
                    confidence=d["classifier_input"]["confidence"],
                    quality=d["classifier_input"]["quality"],
                    detected_language=d["language"].get("language", ""),
                    platform=d["source"].get("platform", ""),
                    source_ref=(d["source"].get("reference") or "")[:2000],
                    finished_at=utcnow(),
                    duration_seconds=elapsed,
                )
                await self._publish(job_id, {"status": "completed", "progress": 1.0,
                                             "stage": "done", "result": d})
                log.info("[worker %d] job %s completed in %.1fs", idx, job_id, elapsed)

            except asyncio.CancelledError:
                self._update(job_id, status="failed", stage="cancelled",
                             error="Server shut down before the job finished.",
                             finished_at=utcnow())
                raise
            except Exception as exc:
                elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
                msg = str(exc) if isinstance(exc, PipelineError) else f"{type(exc).__name__}: {exc}"
                log.exception("[worker %d] job %s failed", idx, job_id)
                self._update(job_id, status="failed", stage="error", error=msg,
                             finished_at=utcnow(), duration_seconds=elapsed)
                await self._publish(job_id, {"status": "failed", "stage": "error",
                                             "error": msg})
            finally:
                await self._publish(job_id, {"_eof": True})
                self._queue.task_done()

    def _run_sync(self, job_id: str, req: TranscriptionRequest):
        """Runs on a pool thread - blocking is fine here."""
        def progress(pct: float, msg: str) -> None:
            self._update(job_id, progress=round(float(pct), 3), stage=msg[:120])
            if self._loop and not self._loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    self._publish(job_id, {"status": "running",
                                           "progress": round(float(pct), 3),
                                           "stage": msg[:120]}),
                    self._loop,
                )

        return run_pipeline(req, progress=progress)

    # ----------------------------------------------------------------- #
    # state
    # ----------------------------------------------------------------- #
    @staticmethod
    def _update(job_id: str, **fields) -> None:
        try:
            with session_scope() as s:
                row = s.get(TranscriptionJob, job_id)
                if row is None:
                    return
                for k, v in fields.items():
                    setattr(row, k, v)
        except Exception:
            log.exception("Could not persist job update for %s", job_id)

    @staticmethod
    def get(job_id: str) -> dict | None:
        with session_scope() as s:
            row = s.get(TranscriptionJob, job_id)
            return row.as_dict() if row else None

    @staticmethod
    def list_recent(limit: int = 50, status: str | None = None) -> list[dict]:
        from sqlalchemy import select

        with session_scope() as s:
            stmt = select(TranscriptionJob).order_by(TranscriptionJob.created_at.desc())
            if status:
                stmt = stmt.where(TranscriptionJob.status == status)
            rows = s.scalars(stmt.limit(min(limit, 200))).all()
            return [r.as_dict(include_result=False) for r in rows]

    # ----------------------------------------------------------------- #
    # live progress (SSE)
    # ----------------------------------------------------------------- #
    async def _publish(self, job_id: str, payload: dict) -> None:
        for q in list(self._listeners.get(job_id, ())):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    def subscribe(self, job_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._listeners.setdefault(job_id, set()).add(q)
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        listeners = self._listeners.get(job_id)
        if listeners:
            listeners.discard(q)
            if not listeners:
                self._listeners.pop(job_id, None)


manager = JobManager()
