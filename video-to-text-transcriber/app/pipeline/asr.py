"""Stage 3 - speech recognition.

Model
-----
The scope document specifies OpenAI Whisper large-v3, and that is exactly the
model we run. What we changed is the *runtime*: instead of the reference PyTorch
package (`openai-whisper`) we use faster-whisper, which executes the identical
Whisper weights on the CTranslate2 inference engine. Same architecture, same
checkpoints, same output - roughly 4x the speed at about half the memory,
with int8 quantisation so large-v3 fits on a CPU-only machine at all.

Both are free and fully local. Nothing here calls a paid API. (OpenAI's *hosted*
Whisper endpoint is billed per minute; the Whisper *model* is MIT-licensed and
what we use. Those are two different things and the distinction matters for the
"zero running cost" claim in the proposal.)

Backends
--------
`local`  - run on this machine.
`remote` - forward to another instance of this same service that happens to sit
           on a GPU (a free Colab/Kaggle notebook, tunnelled). Identical API,
           so the calling code never changes. This is how a laptop with no GPU
           still demos large-v3 in near real time.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.config import settings
from app.pipeline import language as lang_mod

log = logging.getLogger(__name__)

ProgressFn = Callable[[float, str], None]

# Whisper size aliases -> what we actually hand to faster-whisper. Anything not
# in this map is passed through verbatim, so a fine-tuned CTranslate2 repo id
# such as "ihanif/faster-whisper-medium-urdu" works with no code change.
_SIZE_ALIASES = {
    "tiny", "tiny.en", "base", "base.en", "small", "small.en",
    "medium", "medium.en", "large-v1", "large-v2", "large-v3",
    "large", "distil-large-v3", "large-v3-turbo", "turbo",
}


class ASRError(RuntimeError):
    pass


@dataclass
class ASRResult:
    segments: list[dict]
    language: str
    language_probability: float
    language_decision: dict
    duration: float
    duration_after_vad: float
    model: str
    device: str
    compute_type: str
    task: str
    elapsed: float = 0.0
    realtime_factor: float = 0.0
    meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Model cache
# --------------------------------------------------------------------------- #
_model_lock = threading.Lock()
_model_cache: dict[tuple, object] = {}


def get_model(model_name: str | None = None):
    """Load (and memoise) a WhisperModel. Thread-safe; first call downloads."""
    from faster_whisper import WhisperModel

    name = model_name or settings.asr_model
    device, compute = settings.resolve_device()
    threads = settings.resolve_cpu_threads()
    key = (name, device, compute, threads)

    if key in _model_cache:
        return _model_cache[key]

    with _model_lock:
        if key in _model_cache:
            return _model_cache[key]
        log.info(
            "Loading Whisper %s on %s (%s, %d threads) - first run downloads weights.",
            name, device, compute, threads,
        )
        t0 = time.perf_counter()
        try:
            model = WhisperModel(
                name,
                device=device,
                compute_type=compute,
                cpu_threads=threads,
                download_root=str(settings.models_dir),
            )
        except Exception as exc:
            raise ASRError(
                f"Could not load Whisper model {name!r} on {device}/{compute}: {exc}"
            ) from exc
        log.info("Model ready in %.1fs", time.perf_counter() - t0)
        _model_cache[key] = model
        return model


def warm_up(model_name: str | None = None) -> dict:
    """Force the model into memory so the first real request is not slow."""
    t0 = time.perf_counter()
    get_model(model_name)
    device, compute = settings.resolve_device()
    return {
        "model": model_name or settings.asr_model,
        "device": device,
        "compute_type": compute,
        "cpu_threads": settings.resolve_cpu_threads(),
        "load_seconds": round(time.perf_counter() - t0, 2),
    }


def model_is_loaded(model_name: str | None = None) -> bool:
    name = model_name or settings.asr_model
    device, compute = settings.resolve_device()
    return (name, device, compute, settings.resolve_cpu_threads()) in _model_cache


# --------------------------------------------------------------------------- #
# Language detection
# --------------------------------------------------------------------------- #
def _vad_options():
    """Build VadOptions.

    Note the asymmetry in faster-whisper: `transcribe()` accepts either a dict or
    a VadOptions, but `detect_language()` accepts only VadOptions and raises an
    AttributeError on a dict. Returning the object keeps both call sites correct.
    """
    from faster_whisper.vad import VadOptions

    return VadOptions(
        threshold=settings.vad_threshold,
        min_silence_duration_ms=settings.vad_min_silence_ms,
        speech_pad_ms=settings.vad_speech_pad_ms,
    )


def detect_language(audio, model=None) -> lang_mod.LanguageDecision:
    """Probe several windows of speech, then apply the Urdu-over-Hindi policy.

    Detecting on one window is fragile for reels: the opening seconds are often
    a music sting or an English hook before the Urdu starts. We sample multiple
    VAD-selected windows so the vote reflects the body of the clip.
    """
    model = model or get_model()
    try:
        detected, prob, all_probs = model.detect_language(
            audio=audio,
            vad_filter=settings.vad_enabled,
            vad_parameters=_vad_options() if settings.vad_enabled else None,
            language_detection_segments=max(1, settings.lang_detect_windows),
            language_detection_threshold=0.5,
        )
    except Exception as exc:
        log.warning("Language detection failed (%s); defaulting to auto.", exc)
        return lang_mod.LanguageDecision("en", 0.0, "en", reason=f"detection failed: {exc}")

    candidates = dict(all_probs) if all_probs else {detected: prob}
    return lang_mod.decide_language(
        candidates,
        urdu_bias=settings.urdu_bias_enabled,
        urdu_min_prob=settings.urdu_bias_min_prob,
        allowed=settings.allowed_language_list,
    )


# --------------------------------------------------------------------------- #
# Transcription
# --------------------------------------------------------------------------- #
def transcribe(
    audio_path: Path,
    *,
    language: str | None = None,
    task: str = "transcribe",
    model_name: str | None = None,
    progress: ProgressFn | None = None,
) -> ASRResult:
    """Run Whisper over a prepared 16 kHz WAV.

    `language=None` means auto-detect (with the Urdu bias applied).
    `task="translate"` makes Whisper output English regardless of input language.
    """
    from faster_whisper.audio import decode_audio

    if settings.asr_backend == "remote":
        return _transcribe_remote(audio_path, language=language, task=task)

    def emit(pct: float, msg: str) -> None:
        if progress:
            try:
                progress(pct, msg)
            except Exception:
                pass

    emit(0.05, "Loading speech model")
    model = get_model(model_name)
    name = model_name or settings.asr_model
    device, compute = settings.resolve_device()

    # Decode once and reuse for detection + transcription.
    try:
        audio = decode_audio(str(audio_path), sampling_rate=16000)
    except Exception as exc:
        raise ASRError(f"Could not decode {audio_path.name}: {exc}") from exc

    total_seconds = len(audio) / 16000.0
    if total_seconds < 0.25:
        raise ASRError("Audio is shorter than 0.25s - nothing to transcribe.")

    # ---- language ----
    if language:
        decision = lang_mod.LanguageDecision(
            language=language, probability=1.0, detected_raw=language,
            reason="explicitly requested by caller",
        )
    else:
        emit(0.15, "Detecting language")
        decision = detect_language(audio, model=model)
        log.info(
            "Language: %s (p=%.2f)%s",
            decision.language, decision.probability,
            " [corrected from hi]" if decision.corrected else "",
        )

    # ---- decode ----
    emit(0.25, f"Transcribing {lang_mod.LANGUAGE_NAMES.get(decision.language, decision.language)}")
    t0 = time.perf_counter()

    try:
        seg_iter, info = model.transcribe(
            audio,
            language=decision.language,
            task=task,
            beam_size=settings.asr_beam_size,
            best_of=settings.asr_beam_size,
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],

            # --- anti-hallucination block ---
            # Letting Whisper condition on its own previous output is the main
            # cause of runaway repetition loops on short musical clips.
            condition_on_previous_text=settings.condition_on_previous_text,
            compression_ratio_threshold=settings.compression_ratio_threshold,
            log_prob_threshold=settings.log_prob_threshold,
            no_speech_threshold=settings.no_speech_threshold,
            # Drop text the model invents over long silences.
            hallucination_silence_threshold=2.0,

            # --- VAD: strip music/silence before the decoder ever sees it ---
            vad_filter=settings.vad_enabled,
            vad_parameters=_vad_options() if settings.vad_enabled else None,

            # Bias the decoder toward Urdu orthography rather than Devanagari.
            initial_prompt=lang_mod.initial_prompt_for(decision.language),

            word_timestamps=settings.word_timestamps,
        )
    except Exception as exc:
        raise ASRError(f"Whisper failed on {audio_path.name}: {exc}") from exc

    # faster-whisper streams lazily, so this loop is where the work happens -
    # which makes it the right place to report progress.
    segments: list[dict] = []
    for seg in seg_iter:
        segments.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
            "avg_logprob": seg.avg_logprob,
            "no_speech_prob": seg.no_speech_prob,
            "compression_ratio": seg.compression_ratio,
            "temperature": getattr(seg, "temperature", 0.0),
            "words": [
                {"word": w.word, "start": w.start, "end": w.end,
                 "probability": round(w.probability, 4)}
                for w in (seg.words or [])
            ] if settings.word_timestamps else [],
        })
        if total_seconds:
            frac = min(0.95, 0.25 + 0.70 * (seg.end / total_seconds))
            emit(frac, f"Transcribing {seg.end:.0f}s / {total_seconds:.0f}s")

    elapsed = time.perf_counter() - t0
    emit(0.97, "Cleaning transcript")

    return ASRResult(
        segments=segments,
        language=decision.language,
        language_probability=decision.probability,
        language_decision=decision.as_dict(),
        duration=round(float(getattr(info, "duration", total_seconds)), 2),
        duration_after_vad=round(float(getattr(info, "duration_after_vad", 0.0) or 0.0), 2),
        model=name,
        device=device,
        compute_type=compute,
        task=task,
        elapsed=round(elapsed, 2),
        realtime_factor=round(total_seconds / elapsed, 2) if elapsed > 0 else 0.0,
        meta={
            "vad_enabled": settings.vad_enabled,
            "beam_size": settings.asr_beam_size,
            "condition_on_previous_text": settings.condition_on_previous_text,
            "initial_prompt_used": bool(lang_mod.initial_prompt_for(decision.language)),
            "cpu_threads": settings.resolve_cpu_threads(),
        },
    )


# --------------------------------------------------------------------------- #
# Remote backend (free GPU offload)
# --------------------------------------------------------------------------- #
def _transcribe_remote(audio_path: Path, *, language: str | None, task: str) -> ASRResult:
    import httpx

    base = settings.remote_asr_url.rstrip("/")
    if not base:
        raise ASRError("ASR_BACKEND=remote but REMOTE_ASR_URL is not set.")

    headers = {}
    if settings.remote_asr_token:
        headers["Authorization"] = f"Bearer {settings.remote_asr_token}"

    t0 = time.perf_counter()
    try:
        with audio_path.open("rb") as fh:
            resp = httpx.post(
                f"{base}/api/v1/transcribe/raw",
                files={"file": (audio_path.name, fh, "audio/wav")},
                data={"language": language or "", "task": task},
                headers=headers,
                timeout=900.0,
            )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        raise ASRError(f"Remote ASR call failed: {exc}") from exc

    return ASRResult(
        segments=payload.get("segments", []),
        language=payload.get("language", "en"),
        language_probability=payload.get("language_probability", 0.0),
        language_decision=payload.get("language_decision", {}),
        duration=payload.get("duration", 0.0),
        duration_after_vad=payload.get("duration_after_vad", 0.0),
        model=payload.get("model", "remote"),
        device=payload.get("device", "remote"),
        compute_type=payload.get("compute_type", "remote"),
        task=task,
        elapsed=round(time.perf_counter() - t0, 2),
        realtime_factor=payload.get("realtime_factor", 0.0),
        meta={"remote": True, "endpoint": base},
    )
