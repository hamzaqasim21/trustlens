"""Locate and drive FFmpeg.

We never assume FFmpeg is on PATH. Resolution order:
  1. FFMPEG_BINARY env var
  2. system `ffmpeg` on PATH
  3. the static binary shipped by the `imageio-ffmpeg` wheel  <- always works, no admin
"""
from __future__ import annotations

import functools
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class FFmpegError(RuntimeError):
    pass


@functools.lru_cache(maxsize=1)
def ffmpeg_path() -> str:
    override = os.environ.get("FFMPEG_BINARY")
    if override and Path(override).exists():
        return override

    found = shutil.which("ffmpeg")
    if found:
        return found

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover
        raise FFmpegError(
            "FFmpeg not found. Install it, or `pip install imageio-ffmpeg` "
            "which bundles a static build (no admin rights needed)."
        ) from exc


@functools.lru_cache(maxsize=1)
def ffprobe_path() -> str | None:
    """ffprobe is optional - we fall back to PyAV for probing."""
    override = os.environ.get("FFPROBE_BINARY")
    if override and Path(override).exists():
        return override
    return shutil.which("ffprobe")


def run(args: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        args,
        capture_output=True,
        timeout=timeout,
        creationflags=_CREATE_NO_WINDOW,
    )
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace")[-1500:]
        raise FFmpegError(f"{Path(args[0]).name} failed (exit {proc.returncode}):\n{tail}")
    return proc


def probe(path: Path) -> dict:
    """Return {duration, has_audio, has_video, width, height}.

    Uses ffprobe when available; otherwise PyAV (a faster-whisper dependency,
    so it is guaranteed to be installed).
    """
    fp = ffprobe_path()
    if fp:
        try:
            proc = run(
                [fp, "-v", "quiet", "-print_format", "json",
                 "-show_format", "-show_streams", str(path)],
                timeout=60,
            )
            data = json.loads(proc.stdout.decode("utf-8", "replace"))
            streams = data.get("streams", [])
            audio = [s for s in streams if s.get("codec_type") == "audio"]
            video = [s for s in streams if s.get("codec_type") == "video"]
            duration = float(data.get("format", {}).get("duration") or 0.0)
            if not duration:
                for s in streams:
                    if s.get("duration"):
                        duration = max(duration, float(s["duration"]))
            return {
                "duration": duration,
                "has_audio": bool(audio),
                "has_video": bool(video),
                "width": int(video[0].get("width") or 0) if video else 0,
                "height": int(video[0].get("height") or 0) if video else 0,
            }
        except Exception as exc:
            log.debug("ffprobe failed, falling back to PyAV: %s", exc)

    return _probe_pyav(path)


def _probe_pyav(path: Path) -> dict:
    import av

    with av.open(str(path)) as container:
        duration = (container.duration or 0) / 1_000_000 if container.duration else 0.0
        audio = list(container.streams.audio)
        video = list(container.streams.video)
        if not duration:
            for s in (audio + video):
                if s.duration and s.time_base:
                    duration = max(duration, float(s.duration * s.time_base))
        w = h = 0
        if video:
            w, h = int(video[0].width or 0), int(video[0].height or 0)
        return {
            "duration": float(duration),
            "has_audio": bool(audio),
            "has_video": bool(video),
            "width": w,
            "height": h,
        }
