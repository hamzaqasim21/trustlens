"""Stage 3b - read burned-in on-screen text when the audio cannot carry the load.

The scope document commits to this explicitly: "In such cases, the system falls
back to analyzing visible on-screen text and post captions." This module is that
fallback.

It earns its place for reasons beyond broken audio. A large share of Pakistani
misinformation reels are *silent* or music-only, with the entire claim burned
into the frame as a caption or a fake news-ticker chyron. Audio-only analysis
misses those completely.

OCR is opt-in (OCR_ENABLED=true) because EasyOCR pulls PyTorch, which is a ~2 GB
install. Everything else in the pipeline works without it. When it is off and a
clip has no usable audio, we say so plainly rather than returning a silent
empty transcript.
"""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from app.config import settings
from app.pipeline.audio import extract_frames
from app.pipeline.language import normalise_text, profile_script

log = logging.getLogger(__name__)


class OCRUnavailable(RuntimeError):
    pass


@dataclass
class OCRResult:
    text: str
    confidence: float
    frames_scanned: int
    lines: list[dict] = field(default_factory=list)
    engine: str = "easyocr"
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "confidence": round(self.confidence, 4),
            "frames_scanned": self.frames_scanned,
            "line_count": len(self.lines),
            "lines": self.lines[:80],
            "engine": self.engine,
            "warnings": self.warnings,
        }


_reader_lock = threading.Lock()
_reader_cache: dict[tuple, object] = {}


def is_available() -> bool:
    try:
        import easyocr  # noqa: F401

        return True
    except Exception:
        return False


def _get_reader(languages: list[str]):
    """EasyOCR restricts which scripts can share one reader, so we degrade gracefully."""
    import easyocr

    key = tuple(sorted(languages))
    if key in _reader_cache:
        return _reader_cache[key]

    with _reader_lock:
        if key in _reader_cache:
            return _reader_cache[key]
        try:
            reader = easyocr.Reader(
                languages, gpu=False, verbose=False,
                model_storage_directory=str(settings.models_dir / "easyocr"),
            )
        except Exception as exc:
            # Arabic-script languages cannot always be mixed with Latin in one
            # reader. Fall back to Urdu alone, which still recognises digits and
            # most Latin characters reasonably well.
            log.warning("EasyOCR reader %s failed (%s); retrying Urdu-only.", languages, exc)
            reader = easyocr.Reader(
                ["ur"], gpu=False, verbose=False,
                model_storage_directory=str(settings.models_dir / "easyocr"),
            )
        _reader_cache[key] = reader
        return reader


def _dedupe(lines: list[str], threshold: float = 0.85) -> list[str]:
    """Collapse the same caption repeated across consecutive sampled frames."""
    kept: list[str] = []
    for line in lines:
        norm = re.sub(r"\s+", " ", line).strip()
        if len(norm) < 2:
            continue
        if any(SequenceMatcher(None, norm, k).ratio() >= threshold for k in kept):
            continue
        kept.append(norm)
    return kept


def read_frames(
    frames: list[Path],
    languages: list[str] | None = None,
    min_confidence: float | None = None,
) -> OCRResult:
    if not frames:
        return OCRResult(text="", confidence=0.0, frames_scanned=0,
                         warnings=["No frames were available to scan."])

    if not is_available():
        raise OCRUnavailable(
            "OCR is enabled but EasyOCR is not installed. "
            "Run: pip install -r requirements-optional.txt"
        )

    languages = languages or settings.ocr_language_list
    min_conf = settings.ocr_min_confidence if min_confidence is None else min_confidence
    reader = _get_reader(languages)

    raw_lines: list[dict] = []
    for idx, frame in enumerate(frames):
        try:
            detections = reader.readtext(str(frame), detail=1, paragraph=False)
        except Exception as exc:
            log.warning("OCR failed on %s: %s", frame.name, exc)
            continue
        for det in detections:
            if len(det) < 3:
                continue
            _, text, conf = det[0], det[1], float(det[2])
            text = normalise_text(str(text))
            if not text or conf < min_conf:
                continue
            raw_lines.append({"frame": idx, "text": text, "confidence": round(conf, 4)})

    if not raw_lines:
        return OCRResult(
            text="", confidence=0.0, frames_scanned=len(frames),
            warnings=["No readable on-screen text was found."],
        )

    unique = _dedupe([ln["text"] for ln in raw_lines])
    text = normalise_text("\n".join(unique))
    confidence = sum(ln["confidence"] for ln in raw_lines) / len(raw_lines)

    warnings: list[str] = []
    prof = profile_script(text)
    if prof.ratio("arabic") > 0.2 and prof.ratio("arabic") < 0.9:
        warnings.append("Mixed-script on-screen text; OCR accuracy on Urdu is lower than English.")

    return OCRResult(
        text=text,
        confidence=confidence,
        frames_scanned=len(frames),
        lines=raw_lines,
        warnings=warnings,
    )


def read_video(video_path: Path, workdir: Path, frame_count: int | None = None) -> OCRResult:
    """Sample frames from a video and OCR them."""
    n = frame_count or settings.ocr_frame_count
    frames = extract_frames(video_path, workdir, count=n)
    if not frames:
        return OCRResult(
            text="", confidence=0.0, frames_scanned=0,
            warnings=["Source has no video stream, so there are no frames to read."],
        )
    return read_frames(frames)


def should_fallback(transcript_text: str, transcript_confidence: float) -> bool:
    """Decide whether the audio transcript is too weak to stand on its own."""
    if not settings.ocr_auto_fallback:
        return False
    if len(transcript_text.strip()) < settings.ocr_fallback_min_chars:
        return True
    return transcript_confidence < settings.ocr_fallback_min_confidence
