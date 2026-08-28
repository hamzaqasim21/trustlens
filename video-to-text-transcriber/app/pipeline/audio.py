"""Stage 2 - turn arbitrary media into Whisper-ready audio.

Whisper wants 16 kHz mono PCM. Beyond the format conversion we apply a light
conditioning chain, because Instagram reels are not clean speech recordings:
they are loud background music, compressed to within an inch of their life,
with the voice sitting well below the mix.

A deliberate note on how far to push this: Whisper was trained on messy,
real-world audio and is already robust to noise. Aggressive denoising strips
formants and measurably *hurts* accuracy. So "light" is the default, and it
only does things that are safe - band-limiting to the speech range and
evening out the level so quiet speech is not lost against loud music.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.pipeline.ffmpeg_tools import FFmpegError, ffmpeg_path, probe, run

log = logging.getLogger(__name__)


class AudioError(RuntimeError):
    pass


@dataclass
class AudioTrack:
    path: Path
    duration: float
    sample_rate: int
    denoise_profile: str
    source_had_video: bool


# FFmpeg filter chains, cheapest first.
#
# highpass/lowpass : keep the speech band; drops sub-bass music thump and hiss
#                    that sits above what a 16 kHz model can even represent.
# dynaudnorm       : gentle *dynamic* normalisation - lifts quiet speech without
#                    pumping the way a hard compressor would.
# afftdn           : FFT noise reduction. Real denoising, but it can smear
#                    consonants, so it is aggressive-only.
_FILTERS = {
    "none": [],
    "light": [
        "highpass=f=80",
        "lowpass=f=7800",
        "dynaudnorm=f=200:g=11:p=0.9:m=8:r=0.9",
    ],
    "aggressive": [
        "highpass=f=100",
        "lowpass=f=7500",
        "afftdn=nr=12:nf=-28:tn=1",
        "dynaudnorm=f=150:g=15:p=0.95:m=12:r=0.9",
        "alimiter=level_in=1:level_out=0.95",
    ],
}


def extract_audio(
    source: Path,
    workdir: Path | None = None,
    denoise: str | None = None,
) -> AudioTrack:
    """Decode `source` to a mono 16 kHz WAV that Whisper can ingest directly."""
    workdir = workdir or source.parent
    profile = denoise or settings.audio_denoise
    if profile not in _FILTERS:
        profile = "light"

    info = probe(source)
    if not info["has_audio"]:
        raise AudioError(
            "This file has no audio track. If it is a silent video, enable the OCR "
            "fallback (OCR_ENABLED=true) to read on-screen text instead."
        )

    duration = float(info.get("duration") or 0.0)
    if duration and duration > settings.max_duration_sec:
        raise AudioError(
            f"Clip is {duration / 60:.1f} min, over the "
            f"{settings.max_duration_sec / 60:.0f} min limit."
        )

    target = workdir / "audio_16k.wav"
    _decode(source, target, profile)

    if not target.exists() or target.stat().st_size < 1024:
        raise AudioError("Audio extraction produced an empty file.")

    if not duration:
        duration = float(probe(target).get("duration") or 0.0)

    return AudioTrack(
        path=target,
        duration=duration,
        sample_rate=settings.audio_sample_rate,
        denoise_profile=profile,
        source_had_video=bool(info["has_video"]),
    )


def _decode(source: Path, target: Path, profile: str) -> None:
    args = [
        ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", str(source),
        "-vn",                                    # drop video
        "-ac", "1",                               # mono
        "-ar", str(settings.audio_sample_rate),   # 16 kHz
        "-acodec", "pcm_s16le",
    ]
    chain = _FILTERS[profile]
    if chain:
        args += ["-af", ",".join(chain)]
    args.append(str(target))

    try:
        run(args)
    except FFmpegError as exc:
        # A broken filter chain should never cost us the transcript - retry raw.
        if chain:
            log.warning("Filtered decode failed (%s); retrying without filters.", exc)
            _decode(source, target, "none")
            return
        raise AudioError(f"FFmpeg could not decode the audio: {exc}") from exc


def extract_frames(
    source: Path,
    workdir: Path,
    count: int = 12,
    max_width: int = 960,
) -> list[Path]:
    """Sample `count` evenly spaced frames, for the OCR fallback path."""
    info = probe(source)
    if not info["has_video"]:
        return []

    duration = float(info.get("duration") or 0.0)
    out_dir = workdir / "frames"
    out_dir.mkdir(parents=True, exist_ok=True)

    if duration <= 0:
        fps_expr = "1"
    else:
        # Spread `count` samples across the clip.
        fps_expr = f"{max(count / duration, 0.05):.6f}"

    args = [
        ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", str(source),
        "-vf", f"fps={fps_expr},scale='min({max_width},iw)':-2",
        "-frames:v", str(count),
        "-q:v", "2",
        str(out_dir / "frame_%03d.jpg"),
    ]
    try:
        run(args, timeout=300)
    except FFmpegError as exc:
        log.warning("Frame extraction failed: %s", exc)
        return []

    return sorted(out_dir.glob("frame_*.jpg"))
