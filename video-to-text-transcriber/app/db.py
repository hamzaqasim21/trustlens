"""Persistence.

SQLAlchemy is used so the same code runs on SQLite during development and on the
PostgreSQL instance the scope document specifies for production - switching is a
one-line change to DATABASE_URL, no code edits.

Two things live here:
  * TranscriptionJob - the job record, so a result survives a restart and the
    dashboard can poll for it.
  * the cache        - keyed on a content fingerprint. The proposal calls for
    caching to avoid redundant work; re-analysing the same reel is pure waste,
    and on a CPU-only box it is minutes of waste.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    JSON, DateTime, Float, Integer, String, Text, create_engine, func, select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TranscriptionJob(Base):
    __tablename__ = "transcription_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True, default="")

    status: Mapped[str] = mapped_column(String(16), index=True, default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    stage: Mapped[str] = mapped_column(String(120), default="queued")

    source_kind: Mapped[str] = mapped_column(String(16), default="")
    source_ref: Mapped[str] = mapped_column(Text, default="")
    platform: Mapped[str] = mapped_column(String(24), default="")

    requested_language: Mapped[str] = mapped_column(String(8), default="")
    task: Mapped[str] = mapped_column(String(16), default="transcribe")
    model: Mapped[str] = mapped_column(String(64), default="")

    detected_language: Mapped[str] = mapped_column(String(8), default="")
    transcript_text: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    quality: Mapped[str] = mapped_column(String(16), default="")

    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    cache_hit: Mapped[int] = mapped_column(Integer, default=0)

    def as_dict(self, include_result: bool = True) -> dict:
        d = {
            "job_id": self.id,
            "status": self.status,
            "progress": round(self.progress, 3),
            "stage": self.stage,
            "source": {
                "kind": self.source_kind,
                "reference": self.source_ref,
                "platform": self.platform,
            },
            "requested_language": self.requested_language or None,
            "task": self.task,
            "model": self.model,
            "detected_language": self.detected_language or None,
            "confidence": round(self.confidence, 4),
            "quality": self.quality,
            "error": self.error or None,
            "cache_hit": bool(self.cache_hit),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "processing_seconds": round(self.duration_seconds, 2),
        }
        if include_result and self.result:
            d["result"] = self.result if isinstance(self.result, dict) else json.loads(self.result)
        return d


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        url = settings.sqlalchemy_url
        kwargs: dict = {"future": True, "pool_pre_ping": True}
        if url.startswith("sqlite"):
            # The worker thread and the request thread share the connection.
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, **kwargs)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _SessionLocal


@contextmanager
def session_scope():
    factory = get_session_factory()
    s = factory()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def init_db() -> None:
    Base.metadata.create_all(get_engine())


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #
def find_cached(fingerprint: str) -> TranscriptionJob | None:
    if not settings.cache_enabled or not fingerprint:
        return None
    with session_scope() as s:
        stmt = (
            select(TranscriptionJob)
            .where(
                TranscriptionJob.fingerprint == fingerprint,
                TranscriptionJob.status == "completed",
            )
            .order_by(TranscriptionJob.finished_at.desc())
            .limit(1)
        )
        return s.scalars(stmt).first()


def purge_old_jobs() -> int:
    """Drop finished jobs past the retention window."""
    cutoff = utcnow() - timedelta(hours=settings.job_retention_hours)
    with session_scope() as s:
        rows = s.scalars(
            select(TranscriptionJob).where(
                TranscriptionJob.created_at < cutoff,
                TranscriptionJob.status.in_(("completed", "failed")),
            )
        ).all()
        for r in rows:
            s.delete(r)
        return len(rows)


def stats() -> dict:
    with session_scope() as s:
        total = s.scalar(select(func.count(TranscriptionJob.id))) or 0
        by_status = dict(
            s.execute(
                select(TranscriptionJob.status, func.count(TranscriptionJob.id))
                .group_by(TranscriptionJob.status)
            ).all()
        )
        avg_conf = s.scalar(
            select(func.avg(TranscriptionJob.confidence))
            .where(TranscriptionJob.status == "completed")
        )
        by_lang = dict(
            s.execute(
                select(TranscriptionJob.detected_language, func.count(TranscriptionJob.id))
                .where(TranscriptionJob.status == "completed")
                .group_by(TranscriptionJob.detected_language)
            ).all()
        )
        return {
            "total_jobs": total,
            "by_status": by_status,
            "by_language": {k or "unknown": v for k, v in by_lang.items()},
            "mean_confidence": round(float(avg_conf), 4) if avg_conf else 0.0,
        }
