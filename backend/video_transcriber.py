"""
Module 12 - Video-to-Text Transcriber (website side).

Takes the sound of an Instagram reel and turns the speech into text, so the
misinformation check can read what is SAID in a reel, not only its caption.

Pipeline for one reel:
  1. download   - the reel's audio-only track (from Instagram's streaming
                  description, ~0.5 MB a minute); the video file if there is
                  no separate audio track. Only the first 45 seconds are needed.
  2. language   - Whisper guesses the language; if it says Hindi but Urdu is
                  also likely, Urdu is used (urdu_language.py).
  3. transcribe - Whisper (faster-whisper, runs on the CPU), with voice
                  detection so music and silence are skipped rather than
                  "heard" as words, and an Urdu-script start for Urdu speech.
  4. clean up   - segments Whisper itself doubts are dropped; Hindi script is
                  converted to Urdu script for Urdu speech.
  5. grade      - "good" (clear speech), "rough" (unclear: shown to the user
                  but never used in the score) or "none" (no speech).

What this is and isn't, for the panel: Whisper is a pretrained speech model
used as-is (OpenAI, Radford et al. 2022), not trained by us. It only produces
text. The judging is done by our own misinformation classifier + red flags.

The same speech model files as the browser extension are used (downloaded
once into browser_extension/gateway/models/).
"""
from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from collections import OrderedDict
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

import urdu_language as ul

log = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
MODELS_DIR = _HERE / "browser_extension" / "gateway" / "models"
TMP_DIR = _HERE / ".tmp_audio"

# Model sizes, measured on this PC on real Urdu and English reels (2026-10-21):
#   base  - 2.7-8 s a reel; English near-perfect, Urdu understandable with
#           misheard words.
#   small - Urdu clearly better, but 9-27 s a reel on its own and 41.5 s for
#           one 31 s reel inside a live scan (sharing the CPU with the
#           misinformation model) - a 68 s scan in the browser test.
# So every reel uses "base" by default. Urdu speech only counts toward the
# score when a red-flag rule backs it (scan_service._unbacked_urdu_label), so
# the better Urdu wording would rarely change a score. Set
# WEBSITE_WHISPER_CAREFUL=small in .env to listen to a pasted reel with "small".
QUICK_MODEL = os.getenv("WEBSITE_WHISPER_QUICK", "base")
CAREFUL_MODEL = os.getenv("WEBSITE_WHISPER_CAREFUL", "base")
CPU_THREADS = int(os.getenv("WEBSITE_WHISPER_THREADS", "4"))
MAX_AUDIO_SECONDS = 45.0          # scam pitches come early; same as the extension
SAMPLE_RATE = 16000
MAX_DOWNLOAD_BYTES = 30 * 1024 * 1024

# A transcript only counts toward the Trust Score when it is clear speech.
# Measured in the extension: on a music/crowd reel Whisper "heard" a political
# sentence at 28% language confidence. Unclear speech is shown, never scored.
MIN_LANGUAGE_PROB = 0.5
MIN_MEAN_LOGPROB = -1.0

_models: dict = {}
_model_error: str | None = None
_load_lock = threading.Lock()
_run_lock = threading.Lock()      # one transcription at a time on the CPU
_cache: "OrderedDict[str, dict]" = OrderedDict()
_CACHE_MAX = 300

try:
    import faster_whisper  # noqa: F401
    _IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #
def _get_model(size: str):
    global _model_error
    with _load_lock:
        if size not in _models:
            from faster_whisper import WhisperModel
            try:
                MODELS_DIR.mkdir(parents=True, exist_ok=True)
                _models[size] = WhisperModel(size, device="cpu", compute_type="int8",
                                             cpu_threads=CPU_THREADS, download_root=str(MODELS_DIR))
                _model_error = None
            except Exception as exc:
                _model_error = f"{type(exc).__name__}: {exc}"
                raise
    return _models[size]


def warm_up() -> None:
    """Load the speech model as the server starts, so the first scan doesn't
    also pay for loading it."""
    if _IMPORT_ERROR:
        log.warning("faster-whisper not installed: %s", _IMPORT_ERROR)
        return
    try:
        _get_model(QUICK_MODEL)
        log.info("Whisper %s loaded for the website", QUICK_MODEL)
    except Exception as exc:
        log.warning("Whisper failed to load: %s", exc)


def status() -> dict:
    if _IMPORT_ERROR:
        return {"available": False, "error": _IMPORT_ERROR}
    if _model_error:
        return {"available": False, "error": _model_error}
    return {"available": True, "quick_model": f"whisper-{QUICK_MODEL}",
            "careful_model": f"whisper-{CAREFUL_MODEL}", "loaded": sorted(_models)}


# --------------------------------------------------------------------------- #
# Download
# --------------------------------------------------------------------------- #
class _IPv4Adapter(HTTPAdapter):
    """Binds connections to an IPv4 address. Measured on this network: IPv6 to
    Instagram's video servers is broken, so each new connection waited ~5 s
    for IPv6 to fail first. Only this downloader is affected."""

    def init_poolmanager(self, *args, **kwargs):
        kwargs["source_address"] = ("0.0.0.0", 0)
        return super().init_poolmanager(*args, **kwargs)


_http = requests.Session()
_http.headers["User-Agent"] = "Mozilla/5.0"
_http.mount("https://", _IPv4Adapter())


def _get_range(url: str, start: int, end: int) -> tuple[bytes, int | None]:
    # Short timeouts: the pieces fetched are small (an audio track's first
    # 2 MB arrives in about a second), so a connection silent for 10 s is dead.
    last = None
    for _ in range(2):
        try:
            r = _http.get(url, headers={"Range": f"bytes={start}-{end}"}, timeout=(4, 10))
            r.raise_for_status()
            cr = r.headers.get("Content-Range", "")
            tail = cr.split("/")[-1] if "/" in cr else ""
            return r.content, (int(tail) if tail.isdigit() else None)
        except requests.RequestException as exc:
            last = exc
    raise RuntimeError(f"download failed ({type(last).__name__})")


def _download(url: str, is_audio_track: bool) -> str:
    """Saves just enough of the file to cover the first MAX_AUDIO_SECONDS.

    Instagram's files keep their index at the start and the servers send byte
    ranges, so the beginning of a file plays on its own. The audio track is
    small (45 s is well under 1 MB), so 2 MB is fetched; for a video file the
    duration is read from the first 1 MB and only the share needed is fetched.
    """
    TMP_DIR.mkdir(exist_ok=True)
    fd, path = tempfile.mkstemp(suffix=".mp4", prefix="reel_", dir=str(TMP_DIR))
    os.close(fd)
    try:
        first_size = 2 * 1024 * 1024 if is_audio_track else 1024 * 1024
        first, total = _get_range(url, 0, first_size - 1)
        with open(path, "wb") as f:
            f.write(first)
        total = total or len(first)
        if not is_audio_track and total > len(first):
            import av
            budget = min(total, MAX_DOWNLOAD_BYTES)
            try:
                with av.open(path) as c:
                    duration = (c.duration or 0) / av.time_base
                if duration > 0:
                    share = min(1.0, (MAX_AUDIO_SECONDS + 3) / duration)
                    budget = min(budget, int(total * share) + 256 * 1024)
            except Exception:
                pass
            if budget > len(first):
                rest, _ = _get_range(url, len(first), budget - 1)
                with open(path, "ab") as f:
                    f.write(rest)
        return path
    except Exception:
        _remove(path)
        raise


def _remove(path: str | None) -> None:
    if path:
        try:
            os.remove(path)
        except OSError:
            pass


# --------------------------------------------------------------------------- #
# Speech to text
# --------------------------------------------------------------------------- #
def _decode(path: str):
    from faster_whisper.audio import decode_audio
    audio = decode_audio(path, sampling_rate=SAMPLE_RATE)
    return audio[: int(MAX_AUDIO_SECONDS * SAMPLE_RATE)], len(audio) / SAMPLE_RATE


def transcribe_audio(audio, total_seconds: float | None = None, size: str | None = None) -> dict:
    """Whisper on a 16 kHz mono array (first 45 s). No downloading here, so
    this part can be tested on its own."""
    size = size or QUICK_MODEL
    model = _get_model(size)
    heard = len(audio) / SAMPLE_RATE
    if heard < 0.5:
        return _no_speech(heard, total_seconds, "the audio is too short to contain speech", size)

    # Language: Whisper's guess over the speech parts, then the Urdu rule.
    try:
        _, _, all_probs = model.detect_language(
            audio=audio, vad_filter=True, language_detection_segments=2)
        decision = ul.decide_language(dict(all_probs or []))
    except Exception:
        # No speech found to detect a language from.
        decision = ul.decide_language({})

    segments, info = model.transcribe(
        audio,
        language=decision["language"],
        beam_size=1,
        # One decoding pass. Whisper's default retries unclear audio at up to
        # six "temperatures"; measured: 35 s for one 45 s reel. Unclear audio
        # is graded "rough" below instead of being retried.
        temperature=0.0,
        vad_filter=True,                    # skip music/silence instead of inventing words
        condition_on_previous_text=False,   # the main cause of repetition loops
        initial_prompt=ul.initial_prompt_for(decision["language"]),
    )

    kept, logprobs = [], []
    for seg in segments:
        # Whisper's classic failure on music: confidently "hearing" words that
        # aren't there. Drop what it itself doubts, and repetition loops.
        if seg.no_speech_prob > 0.6 and seg.avg_logprob < -0.8:
            continue
        if seg.compression_ratio > 2.4:
            continue
        text = seg.text.strip()
        if text:
            kept.append(text)
            logprobs.append(seg.avg_logprob)

    language = decision["language"] or info.language
    probability = decision["probability"] if decision["language"] else float(info.language_probability or 0)
    text = ul.clean(" ".join(kept))
    text, converted = ul.repair_script(text, language)
    if not text:
        return _no_speech(heard, total_seconds, "no speech was found (music, silence or noise)", size)

    mean_lp = sum(logprobs) / len(logprobs)
    reliable = probability >= MIN_LANGUAGE_PROB and mean_lp > MIN_MEAN_LOGPROB
    if reliable:
        quality_note = "Clear speech."
    elif probability < MIN_LANGUAGE_PROB:
        quality_note = "Unclear: the speech model was unsure which language this is (often music or noise)."
    else:
        quality_note = "Unclear: the speech model was unsure of the words (often music or noise)."
    return {
        "available": True,
        "text": text,
        "no_speech": False,
        "language": language,
        "language_name": ul.language_name(language),
        "language_probability": round(probability, 3),
        "language_corrected": decision["corrected"],
        "language_note": decision["reason"],
        "script_converted": converted,
        "quality": "good" if reliable else "rough",
        "quality_note": quality_note,
        "is_reliable": reliable,
        "word_count": len(text.split()),
        "listened_seconds": round(heard, 1),
        "audio_seconds": round(total_seconds, 1) if total_seconds else None,
        "engine": f"whisper-{size}",
    }


def _no_speech(heard, total, note, size) -> dict:
    return {
        "available": True, "text": "", "no_speech": True,
        "language": None, "language_name": None, "language_probability": None,
        "language_corrected": False, "language_note": "", "script_converted": False,
        "quality": "none", "quality_note": note.capitalize() + ".", "is_reliable": False,
        "word_count": 0, "listened_seconds": round(heard, 1),
        "audio_seconds": round(total, 1) if total else None,
        "engine": f"whisper-{size}",
    }


def transcribe_reel(code: str, audio_url: str = "", video_url: str = "",
                    careful: bool = False) -> dict:
    """Blocking. Downloads one reel's sound and transcribes it. Never raises:
    a failure comes back as {"available": False, "error": ...}.
    careful=True uses the larger, slower model (one submitted reel)."""
    size = CAREFUL_MODEL if careful else QUICK_MODEL
    key = f"{size}:{code}"
    if key in _cache:
        return _cache[key]
    if _IMPORT_ERROR:
        return {"available": False, "error": "the speech model isn't installed on this server"}
    sources = [(u, True) for u in [audio_url] if u] + [(u, False) for u in [video_url] if u]
    if not sources:
        return {"available": False, "error": "no audio for this post"}

    started = time.monotonic()
    with _run_lock:
        if key in _cache:
            return _cache[key]
        last = None
        for url, is_audio in sources:
            path = None
            try:
                path = _download(url, is_audio)
                audio, total = _decode(path)
                result = transcribe_audio(audio, total, size)
                result["via"] = "audio track" if is_audio else "video file"
                result["elapsed_seconds"] = round(time.monotonic() - started, 1)
                _cache[key] = result
                while len(_cache) > _CACHE_MAX:
                    _cache.popitem(last=False)
                return result
            except Exception as exc:
                last = exc
                log.warning("Transcribing %s via %s failed: %s",
                            code, "audio" if is_audio else "video", exc)
            finally:
                _remove(path)
    return {"available": False, "error": f"couldn't get this reel's audio ({last})"}
