"""Request/response models for the public API."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class TranscribeUrlRequest(BaseModel):
    url: str = Field(..., description="Instagram reel/post link (TikTok also supported)")
    language: str | None = Field(
        None, description="Force a language code (e.g. 'ur', 'en'). Omit to auto-detect."
    )
    task: Literal["transcribe", "translate"] = Field(
        "transcribe",
        description="'translate' makes Whisper emit English regardless of the source language.",
    )
    model: str | None = Field(None, description="Override the Whisper checkpoint.")
    force_ocr: bool = Field(False, description="Always read on-screen text, not just as a fallback.")
    denoise: Literal["none", "light", "aggressive"] | None = None
    wait: bool = Field(False, description="Block until finished instead of returning a job id.")

    @field_validator("url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        v = (v or "").strip()
        if not v.lower().startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        if len(v) > 2000:
            raise ValueError("url is too long")
        return v

    @field_validator("language")
    @classmethod
    def _check_lang(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip().lower()
        if not (2 <= len(v) <= 5):
            raise ValueError("language must be an ISO code such as 'ur' or 'en'")
        return v


class TranscribeDirectRequest(BaseModel):
    """Used by the browser extension: it already resolved the real media URL."""

    media_url: str = Field(..., description="Direct CDN URL of the video/audio stream")
    page_url: str = Field("", description="The Instagram/TikTok page the media came from")
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Referer / User-Agent to replay. Cookies are intentionally ignored.",
    )
    language: str | None = None
    task: Literal["transcribe", "translate"] = "transcribe"
    force_ocr: bool = False
    wait: bool = False

    @field_validator("media_url")
    @classmethod
    def _check(cls, v: str) -> str:
        v = (v or "").strip()
        if not v.lower().startswith(("http://", "https://", "blob:")):
            raise ValueError("media_url must be an http(s) URL")
        return v

    @model_validator(mode="after")
    def _strip_blob(self):
        if self.media_url.startswith("blob:"):
            raise ValueError(
                "blob: URLs only exist inside the page and cannot be fetched by the "
                "server. The extension must read the blob and upload the bytes instead."
            )
        return self


class JobSubmitted(BaseModel):
    job_id: str
    status: str
    cache_hit: bool = False
    poll_url: str
    stream_url: str
    message: str = ""


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    progress: float
    stage: str
    source: dict[str, Any]
    requested_language: str | None = None
    task: str
    model: str
    detected_language: str | None = None
    confidence: float
    quality: str
    error: str | None = None
    cache_hit: bool = False
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    processing_seconds: float = 0.0
    result: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    asr: dict[str, Any]
    ffmpeg: dict[str, Any]
    ocr: dict[str, Any]
    queue: dict[str, Any]
    database: dict[str, Any]


class ErrorResponse(BaseModel):
    detail: str
    hint: str | None = None
