"""The pipeline itself: media in, classifier-ready text out.

    acquire -> audio -> ASR -> post-process -> [OCR fallback] -> package

The output contract is deliberately shaped for the next module in the chain.
`classifier_input` is the single field the Misinformation Classifier consumes;
everything else is provenance and diagnostics so a low-quality transcript can be
down-weighted instead of silently trusted.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.config import settings
from app.pipeline import acquire, asr, language as lang_mod, ocr, postprocess
from app.pipeline.audio import AudioError, extract_audio
from app.pipeline.chunking import chunk_segments
from app.pipeline.ffmpeg_tools import probe

log = logging.getLogger(__name__)

ProgressFn = Callable[[float, str], None]


class PipelineError(RuntimeError):
    pass


@dataclass
class TranscriptionRequest:
    url: str | None = None
    upload_path: Path | None = None
    upload_name: str = ""
    direct_url: str | None = None
    direct_headers: dict = field(default_factory=dict)
    source_page: str = ""
    language: str | None = None          # None = auto-detect
    task: str = "transcribe"             # transcribe | translate
    force_ocr: bool = False
    denoise: str | None = None
    model: str | None = None


@dataclass
class TranscriptionOutput:
    status: str
    source: dict
    media: dict
    language: dict
    transcript: dict
    ocr: dict | None
    classifier_input: dict
    timings: dict
    engine: dict
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "source": self.source,
            "media": self.media,
            "language": self.language,
            "transcript": self.transcript,
            "ocr": self.ocr,
            "classifier_input": self.classifier_input,
            "timings": self.timings,
            "engine": self.engine,
            "warnings": self.warnings,
        }


def content_fingerprint(req: TranscriptionRequest) -> str:
    """Stable key for the cache.

    Uploads hash the actual bytes, so re-uploading the same file hits the cache
    even under a different filename. URLs hash the URL.
    """
    h = hashlib.sha256()
    if req.upload_path and req.upload_path.exists():
        with req.upload_path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    else:
        h.update((req.url or req.direct_url or "").encode("utf-8"))
    h.update(f"|{req.language or 'auto'}|{req.task}|{req.model or settings.asr_model}".encode())
    return h.hexdigest()


def run_pipeline(req: TranscriptionRequest, progress: ProgressFn | None = None) -> TranscriptionOutput:
    timings: dict[str, float] = {}
    warnings: list[str] = []
    t_start = time.perf_counter()

    def emit(pct: float, msg: str) -> None:
        if progress:
            try:
                progress(pct, msg)
            except Exception:
                pass

    # ---------------- 1. acquire ----------------
    emit(0.02, "Fetching media")
    t0 = time.perf_counter()
    workdir = acquire.new_workdir()
    try:
        asset = _acquire(req, workdir)
    except acquire.AcquisitionError as exc:
        _cleanup(workdir)
        raise PipelineError(str(exc)) from exc
    timings["acquire"] = round(time.perf_counter() - t0, 2)

    try:
        info = probe(asset.path)
        asset.duration = float(info.get("duration") or 0.0)
        asset.has_audio = bool(info.get("has_audio"))
        asset.has_video = bool(info.get("has_video"))
        asset.width, asset.height = info.get("width", 0), info.get("height", 0)

        # ---------------- 2. audio ----------------
        emit(0.12, "Extracting audio")
        t0 = time.perf_counter()
        track = None
        audio_error: str | None = None
        try:
            track = extract_audio(asset.path, workdir, denoise=req.denoise)
            if not asset.duration:
                asset.duration = track.duration
        except AudioError as exc:
            audio_error = str(exc)
            warnings.append(f"Audio stage: {audio_error}")
        timings["audio"] = round(time.perf_counter() - t0, 2)

        # ---------------- 3. ASR ----------------
        clean = None
        asr_result = None
        if track is not None:
            t0 = time.perf_counter()
            try:
                asr_result = asr.transcribe(
                    track.path,
                    language=req.language,
                    task=req.task,
                    model_name=req.model,
                    progress=lambda p, m: emit(0.15 + 0.65 * p, m),
                )
            except asr.ASRError as exc:
                audio_error = str(exc)
                warnings.append(f"ASR stage: {audio_error}")
            timings["asr"] = round(time.perf_counter() - t0, 2)

        # ---------------- 4. post-process ----------------
        script_report: dict = {"applied": False, "method": "none"}
        if asr_result is not None:
            emit(0.84, "Filtering hallucinations")
            t0 = time.perf_counter()
            clean = postprocess.clean_transcript(
                asr_result.segments,
                no_speech_threshold=settings.no_speech_threshold,
                logprob_threshold=settings.log_prob_threshold,
                compression_threshold=settings.compression_ratio_threshold,
            )
            # Repair Devanagari-for-Urdu before anything downstream sees the text.
            if req.task == "transcribe":
                repaired, script_report = lang_mod.repair_script(clean.text, asr_result.language)
                if script_report.get("applied"):
                    clean.text = repaired
                    warnings.append(script_report["note"])
            warnings.extend(clean.warnings)
            timings["postprocess"] = round(time.perf_counter() - t0, 2)

        # ---------------- 5. OCR fallback ----------------
        ocr_result = None
        transcript_text = clean.text if clean else ""
        transcript_conf = clean.confidence if clean else 0.0

        needs_ocr = req.force_ocr or (
            asset.has_video and (
                audio_error is not None
                or ocr.should_fallback(transcript_text, transcript_conf)
            )
        )
        if needs_ocr:
            if settings.ocr_enabled or req.force_ocr:
                emit(0.88, "Reading on-screen text")
                t0 = time.perf_counter()
                try:
                    ocr_result = ocr.read_video(asset.path, workdir)
                    if ocr_result.text:
                        warnings.append(
                            "Audio transcript was weak, so on-screen text was extracted "
                            "as supporting evidence."
                        )
                except ocr.OCRUnavailable as exc:
                    warnings.append(str(exc))
                except Exception as exc:
                    log.warning("OCR failed: %s", exc)
                    warnings.append(f"OCR stage failed: {exc}")
                timings["ocr"] = round(time.perf_counter() - t0, 2)
            else:
                warnings.append(
                    "Audio produced little usable speech and this clip has burned-in "
                    "visuals. Set OCR_ENABLED=true to read on-screen text as a fallback."
                )

        # ---------------- 6. package ----------------
        if clean is None and (ocr_result is None or not ocr_result.text):
            raise PipelineError(
                audio_error or "No transcript could be produced from this media."
            )

        emit(0.97, "Packaging result")
        out = _package(
            asset=asset, track=track, asr_result=asr_result, clean=clean,
            ocr_result=ocr_result, script_report=script_report, req=req,
            timings=timings, warnings=warnings,
        )
        timings["total"] = round(time.perf_counter() - t_start, 2)
        out.timings = timings
        emit(1.0, "Done")
        return out

    finally:
        if not settings.keep_media_files:
            _cleanup(workdir)


def _acquire(req: TranscriptionRequest, workdir: Path):
    if req.upload_path:
        return acquire.register_upload(req.upload_path, req.upload_name or req.upload_path.name)
    if req.direct_url:
        return acquire.fetch_direct(
            req.direct_url, headers=req.direct_headers,
            workdir=workdir, source_page=req.source_page,
        )
    if req.url:
        return acquire.fetch_from_url(req.url, workdir)
    raise PipelineError("No media source supplied: provide a url, a file, or a direct_url.")


def _cleanup(workdir: Path) -> None:
    try:
        shutil.rmtree(workdir, ignore_errors=True)
    except Exception:
        pass


def _package(*, asset, track, asr_result, clean, ocr_result, script_report,
             req, timings, warnings) -> TranscriptionOutput:
    transcript_text = clean.text if clean else ""
    transcript_conf = clean.confidence if clean else 0.0
    quality = clean.quality if clean else "unusable"

    # What the Misinformation Classifier actually reads. When speech is weak but
    # on-screen text is solid, the OCR text is appended rather than substituted -
    # a reel often says one thing and captions another, and both are evidence.
    parts: list[str] = []
    sources: list[str] = []
    if transcript_text:
        parts.append(transcript_text)
        sources.append("speech")
    if ocr_result and ocr_result.text:
        parts.append(ocr_result.text)
        sources.append("on_screen_text")

    combined = "\n\n".join(parts).strip()
    if ocr_result and ocr_result.text and transcript_conf < 0.4:
        effective_conf = max(transcript_conf, ocr_result.confidence * 0.8)
    else:
        effective_conf = transcript_conf

    lang = asr_result.language if asr_result else "unknown"

    # Split into windows the classifier can actually ingest. XLM-RoBERTa caps at
    # 512 tokens and truncates silently past that, so a long video would lose its
    # tail without anyone noticing.
    chunked = chunk_segments(clean.as_dict()["segments"] if clean else [])

    return TranscriptionOutput(
        status="completed",
        source={
            "kind": asset.source_kind,
            "reference": asset.source_ref,
            "platform": asset.platform,
            "title": asset.title,
            "uploader": asset.uploader,
            "page_url": req.source_page or asset.meta.get("webpage_url") or "",
        },
        media={
            "duration_seconds": round(asset.duration, 2),
            "has_audio": asset.has_audio,
            "has_video": asset.has_video,
            "width": asset.width,
            "height": asset.height,
            "denoise_profile": track.denoise_profile if track else None,
        },
        language={
            **(asr_result.language_decision if asr_result else
               {"language": "unknown", "language_name": "Unknown"}),
            "script_repair": script_report,
            "code_switched": bool(
                clean and any(s.code_switched for s in clean.segments if not s.dropped)
            ),
        },
        transcript=(clean.as_dict(include_words=False) if clean else {
            "text": "", "segments": [], "confidence": 0.0, "quality": "unusable",
            "kept_segments": 0, "dropped_segments": 0, "speech_seconds": 0.0,
            "warnings": [], "stats": {},
        }),
        ocr=(ocr_result.as_dict() if ocr_result else None),
        classifier_input={
            "text": combined,
            "language": lang,
            "sources": sources,
            "confidence": round(effective_conf, 4),
            "quality": quality,
            "is_reliable": quality in ("good", "fair") and bool(combined),
            "char_count": len(combined),
            # Feed these to XLM-RoBERTa, not `text`, whenever chunk_count > 1.
            # Each chunk fits the 512-token window and carries its own timestamps
            # and confidence, so a flagged chunk maps back to a moment in the video.
            **chunked.as_dict(),
        },
        timings=timings,
        engine={
            "model": asr_result.model if asr_result else settings.asr_model,
            "device": asr_result.device if asr_result else None,
            "compute_type": asr_result.compute_type if asr_result else None,
            "task": req.task,
            "realtime_factor": asr_result.realtime_factor if asr_result else 0.0,
            "asr_seconds": asr_result.elapsed if asr_result else 0.0,
            **(asr_result.meta if asr_result else {}),
        },
        warnings=_dedupe_warnings(warnings),
    )


def _dedupe_warnings(items: list[str]) -> list[str]:
    seen, out = set(), []
    for w in items:
        if w and w not in seen:
            seen.add(w)
            out.append(w)
    return out
