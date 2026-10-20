"""
Reel audio -> text, inside the gateway.

The gateway used to hand this to a separate transcriber service on port 8000
(Module 12, Ali's). That service is not on this machine, and port 8000 is the
TrustLens website's own port anyway, so "Listen to audio" could only ever fail.

This does the same job in-process with faster-whisper (Whisper, re-implemented
on CTranslate2; runs on CPU). The video comes from the direct CDN link RapidAPI
returns for the reel, so no browser cookies, yt-dlp or page scraping are needed.

What this is and isn't, for the panel: Whisper is a pretrained speech
recognition model used as-is (not trained by us). Its output is only text; the
judging is still done by our own misinformation classifier and red-flag rules.
"""
from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

# "base" measured on this PC: an 82s reel in 4.5s using ~1.6 GB. "small" took
# 11s and ~2.9 GB, and with the classifier also loaded that pushed the machine
# out of memory (the classifier service was killed). English transcripts were
# practically identical. Set WHISPER_MODEL=small in .env for better Urdu.
MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")
CPU_THREADS = int(os.getenv("WHISPER_THREADS", "4"))
# Kept next to the gateway (on the project drive) rather than in the user's
# C:\ profile/temp folders, which on this machine were nearly full.
_HERE = Path(__file__).resolve().parent
MODELS_DIR = _HERE / "models"
TMP_DIR = _HERE / ".tmp"
MAX_DOWNLOAD_BYTES = 80 * 1024 * 1024
# Scam pitches come early in a reel, and download + listening time grow with
# length, so only the first 45 seconds are heard (was 60 — a friend's slower
# connection spent over a minute just downloading). The badge says so when a
# video is longer.
MAX_AUDIO_SECONDS = float(os.getenv("WHISPER_MAX_SECONDS", "45"))

_model = None
_model_error: str | None = None
_load_lock = threading.Lock()
# One transcription at a time: two at once on a laptop CPU makes both slower.
_run_lock = threading.Lock()
# Reels queued behind the one being transcribed, as (code, on_screen).
# "on_screen" jobs are the reel you are looking at; the rest are pre-checks of
# reels you haven't reached yet. A pre-check always gives way to an on-screen
# reel, and an on-screen reel you've swiped past gives way to the new one.
_waiting: list[tuple[str, bool]] = []
_waiting_lock = threading.Lock()
_cache: dict[str, dict] = {}


class _MovedOn(Exception):
    pass


def _someone_else_waiting(code: str, on_screen: bool = True) -> bool:
    """Should the job for `code` stop and let another reel go first? Yes when a
    different reel is now on screen and waiting — whether this job was a
    pre-check or a reel the viewer has since swiped past. Pre-checks waiting
    never interrupt anything."""
    with _waiting_lock:
        return any(c != code and w for c, w in _waiting)


def _screen_reel_waiting() -> bool:
    with _waiting_lock:
        return any(w for _, w in _waiting)


# Pre-checks that the viewer has since reached: they stop yielding.
_promoted: set[str] = set()


def promote(code: str) -> None:
    _promoted.add(code)

try:
    import faster_whisper  # noqa: F401
    _IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


def status() -> dict:
    if _IMPORT_ERROR:
        return {"up": False, "error": _IMPORT_ERROR}
    if _model_error:
        return {"up": False, "error": _model_error}
    return {"up": True, "model": f"whisper-{MODEL_SIZE}", "loaded": _model is not None}


def cached(code: str) -> dict | None:
    return _cache.get(code)


def _get_model():
    global _model, _model_error
    with _load_lock:
        if _model is None:
            from faster_whisper import WhisperModel
            try:
                MODELS_DIR.mkdir(exist_ok=True)
                _model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8",
                                      cpu_threads=CPU_THREADS, download_root=str(MODELS_DIR))
            except Exception as exc:
                _model_error = f"{type(exc).__name__}: {exc}"
                raise
    return _model


def warm_up() -> None:
    """Load the model ahead of the first reel, so the first 'listen' isn't
    also paying for a model load."""
    if _IMPORT_ERROR:
        return
    try:
        _get_model()
        log.info("Whisper %s loaded", MODEL_SIZE)
    except Exception as exc:
        log.warning("Whisper failed to load: %s", exc)


def _force_ipv4() -> None:
    """Measured on this network: IPv6 to Instagram's CDN is broken, so every new
    connection first waited ~5s for IPv6 to fail before falling back to IPv4
    (first byte after 5.7s instead of 0.7s). Only affects this gateway process."""
    import socket
    import urllib3.util.connection as urllib3_conn
    urllib3_conn.allowed_gai_family = lambda: socket.AF_INET


_force_ipv4()
_http = requests.Session()
_http.headers["User-Agent"] = "Mozilla/5.0"
_PIECE = 1024 * 1024
DOWNLOAD_DEADLINE = 25.0      # seconds, whole download
_HEDGE_AFTER = 3.0            # a piece slower than this gets a duplicate request


def _fetch_piece(url: str, start: int, end: int) -> tuple[bytes, int | None]:
    """One byte range, small enough to finish fast. Returns (bytes, total size)."""
    r = _http.get(url, headers={"Range": f"bytes={start}-{end}"}, timeout=(4, 12))
    r.raise_for_status()
    cr = r.headers.get("Content-Range", "")
    total = int(cr.split("/")[-1]) if "/" in cr and cr.split("/")[-1].isdigit() else None
    return r.content, total


def _fetch_all(pool, url: str, ranges: list[tuple[int, int]],
               deadline: float) -> list[tuple[bytes, int | None]]:
    """Fetch byte ranges in parallel. Any piece still missing after
    _HEDGE_AFTER seconds gets a duplicate request, and the first copy to
    arrive wins — measured on this network, the first connection to a CDN edge
    sometimes stalls for 20-30s while a second one finishes in under a second.

    Only this loop waits; the pool threads only download. (An earlier version
    waited inside the pool itself and deadlocked on videos needing more pieces
    than there were threads.)"""
    from concurrent.futures import FIRST_COMPLETED, wait
    results: dict[int, tuple[bytes, int | None]] = {}
    owner: dict = {}                       # future -> piece index
    started: dict[int, list[float]] = {}   # piece index -> start times of its tries
    for i, (a, b) in enumerate(ranges):
        owner[pool.submit(_fetch_piece, url, a, b)] = i
        started[i] = [time.monotonic()]
    last_error = None
    while len(results) < len(ranges):
        if time.monotonic() > deadline:
            raise RuntimeError("couldn't download the video in time (slow network)")
        pending = [f for f, i in owner.items() if i not in results]
        done, _ = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
        for f in done:
            i = owner.pop(f)
            if i in results:
                continue
            try:
                results[i] = f.result()
            except Exception as exc:
                last_error = exc
                if len(started[i]) < 4:            # failed outright: try again
                    owner[pool.submit(_fetch_piece, url, *ranges[i])] = i
                    started[i].append(time.monotonic())
        now = time.monotonic()
        for i in range(len(ranges)):
            if i in results or len(started[i]) >= 3:
                continue
            if now - started[i][-1] > _HEDGE_AFTER:  # slow: race a duplicate
                owner[pool.submit(_fetch_piece, url, *ranges[i])] = i
                started[i].append(now)
        if not owner and len(results) < len(ranges):
            raise RuntimeError(f"couldn't download the video ({type(last_error).__name__})")
    return [results[i] for i in range(len(ranges))]


def _download(url: str, progress) -> tuple[str, float]:
    """Fetch only as much of the reel's video as the first MAX_AUDIO_SECONDS of
    sound needs, as 1 MB pieces fetched in parallel.

    Instagram's MP4s keep their index ("moov") at the front and the CDN serves
    byte ranges, so the first part of the file is a playable video on its own.
    One real "reel" here was 16 minutes / 71 MB; this fetches ~7 MB instead.
    """
    import av
    from concurrent.futures import ThreadPoolExecutor

    TMP_DIR.mkdir(exist_ok=True)
    fd, path = tempfile.mkstemp(suffix=".mp4", prefix="tl_reel_", dir=str(TMP_DIR))
    os.close(fd)
    deadline = time.monotonic() + DOWNLOAD_DEADLINE
    duration = 0.0
    try:
        progress(2, "Downloading the reel…")
        pool = ThreadPoolExecutor(max_workers=12)
        try:
            first, total = _fetch_all(pool, url, [(0, _PIECE - 1)], deadline)[0]
            with open(path, "wb") as f:
                f.write(first)
            total = total or len(first)

            # The index is in the first piece: work out how much covers the
            # first MAX_AUDIO_SECONDS, and fetch only that.
            budget = min(total, 30 * 1024 * 1024)
            try:
                with av.open(path) as c:
                    duration = (c.duration or 0) / av.time_base
                if duration > 0:
                    share = min(1.0, (MAX_AUDIO_SECONDS + 3) / duration)
                    budget = min(total, int(total * share) + 256 * 1024)
            except Exception:
                pass
            if budget > MAX_DOWNLOAD_BYTES:
                raise RuntimeError("Video is too large to transcribe here.")

            ranges = [(a, min(a + _PIECE, budget) - 1) for a in range(len(first), budget, _PIECE)]
            pieces = _fetch_all(pool, url, ranges, deadline) if ranges else []
            with open(path, "ab") as f:
                for data, _ in pieces:         # in order, so the file stays contiguous
                    f.write(data)
        finally:
            # Don't wait for losing duplicate requests; they finish on their own.
            pool.shutdown(wait=False, cancel_futures=True)
        return path, duration
    except Exception:
        _remove(path)
        raise


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _model_on_disk() -> bool:
    return (MODELS_DIR / f"models--Systran--faster-whisper-{MODEL_SIZE}").exists()


def _listen_once(url: str, code: str, on_screen: bool, progress, started: float) -> dict:
    path = None
    try:
        path, video_seconds = _download(url, progress)
        if _someone_else_waiting(code, on_screen):
            raise _MovedOn()
        if _model is None:
            progress(8, "Listening…" if _model_on_disk() else
                     "Getting the speech model ready (first run only, ~150 MB)…")
        else:
            progress(8, "Listening…")
        model = _get_model()

        segments, info = model.transcribe(
            path,
            beam_size=1,
            vad_filter=True,               # skip music/silence instead of inventing words
            condition_on_previous_text=False,
            clip_timestamps=[0, MAX_AUDIO_SECONDS],
        )
        duration = min(float(info.duration or 0.0), MAX_AUDIO_SECONDS) or 1.0

        kept: list[str] = []
        logprobs: list[float] = []
        for seg in segments:
            if _someone_else_waiting(code, on_screen):
                raise _MovedOn()
            if seg.start > MAX_AUDIO_SECONDS:
                break
            # Whisper's classic failure on music: confidently "hearing"
            # words that aren't there. Drop segments it itself doubts.
            if seg.no_speech_prob > 0.6 and seg.avg_logprob < -0.8:
                continue
            text = seg.text.strip()
            if text:
                kept.append(text)
                logprobs.append(seg.avg_logprob)
            pct = 10 + int(88 * min(1.0, seg.end / duration))
            progress(pct, f"Listening… {int(seg.end)}s / {int(duration)}s")

        text = " ".join(kept).strip()
        mean_lp = sum(logprobs) / len(logprobs) if logprobs else -9.0
        lang_p = float(info.language_probability or 0.0)
        reliable = bool(text) and lang_p >= 0.5 and mean_lp > -1.0
        return {
            "available": True,
            "text": text,
            "no_speech": not text,
            "language": info.language,
            "confidence": round(lang_p, 3),
            "quality": "good" if reliable else ("none" if not text else "rough"),
            "is_reliable": reliable,
            "char_count": len(text),
            "audio_seconds": round(float(info.duration or 0.0), 1),
            "listened_seconds": round(min(float(info.duration or 0.0), MAX_AUDIO_SECONDS), 1),
            "video_seconds": round(video_seconds, 1) if video_seconds else None,
            "elapsed_seconds": round(time.monotonic() - started, 1),
            "engine": f"whisper-{MODEL_SIZE}",
        }
    finally:
        if path:
            _remove(path)


def transcribe(code: str, urls, progress, on_screen: bool = True) -> dict:
    """Blocking. `urls` is the audio-only track first (when Instagram's page
    gave us one) then the video; the next is tried if one fails.
    `progress(percent, stage)` is called as it goes. `on_screen` is False for
    pre-checks of reels the viewer hasn't reached yet."""
    if code in _cache:
        return _cache[code]
    if _IMPORT_ERROR:
        return {"available": False, "error": f"faster-whisper not installed ({_IMPORT_ERROR})"}
    urls = [u for u in ([urls] if isinstance(urls, str) else list(urls or [])) if u]
    if not urls:
        return {"available": False, "error": "no video file for this post"}

    started = time.monotonic()
    if not on_screen:
        # A pre-check never jumps ahead of the reel on screen.
        while _screen_reel_waiting() and code not in _promoted:
            time.sleep(0.2)
    entry = (code, on_screen)
    with _waiting_lock:
        _waiting.append(entry)
    try:
        _run_lock.acquire()
    finally:
        with _waiting_lock:
            _waiting.remove(entry)
    try:
        if code in _cache:            # another request finished it while we waited
            return _cache[code]
        last_error = None
        for i, url in enumerate(urls):
            try:
                result = _listen_once(url, code, on_screen, progress, started)
                # Which file was actually heard: the small audio-only track
                # (when Instagram's page provided one) or the video file.
                result["via"] = "audio track" if (len(urls) > 1 and i == 0) else "video file"
                _cache[code] = result
                return result
            except _MovedOn:
                log.info("Stopped listening to %s: a newer reel is waiting", code)
                return {"available": False, "error": "skipped — another reel went first"}
            except Exception as exc:
                last_error = exc
                log.warning("Listening to %s via %s failed: %s", code, url[:60], exc)
        return {"available": False, "error": f"Couldn't transcribe: {last_error}"}
    finally:
        _run_lock.release()
