"""
Thin async clients for the three TrustLens modules.

Design rule: **a module being down must never take the whole verdict down.**
Each client returns a dict that always carries an "available" flag, so the
analyzer can build a partial verdict and say honestly which parts are missing.
That matters because these are three separate services on a laptop, one of them
not being started is the normal case during a demo, not an exception.
"""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from config import settings

log = logging.getLogger(__name__)

# Live transcription progress, keyed by the reel's page URL.
#
# /analyze is one blocking call that can run for minutes, so the badge has no way
# to learn how far along it is. The transcriber already reports exact progress
# ("Transcribing 26s / 56s", 52%) on every poll — this relays it, and the
# extension polls GET /progress to keep the badge honest about what is happening.
# Without it a six-minute wait is indistinguishable from a hang.
PROGRESS: dict[str, dict] = {}


def set_progress(page_url: str, **fields) -> None:
    if not page_url:
        return
    PROGRESS[page_url] = {**PROGRESS.get(page_url, {}), **fields}


def get_progress(page_url: str) -> dict:
    return PROGRESS.get(page_url, {"state": "idle"})


def clear_progress(page_url: str) -> None:
    PROGRESS.pop(page_url, None)


# --------------------------------------------------------------------------- #
# Misinformation classifier  (D:\trustlens_post_checker, port 8001)
# --------------------------------------------------------------------------- #
async def classify_text(text: str) -> dict:
    """Send caption/transcript text to the post checker.

    Returns its full report on success. On failure returns
    {"available": False, "error": ...} rather than raising, so a missing
    classifier degrades the verdict instead of breaking it.
    """
    if not text or not text.strip():
        return {"available": False, "error": "no text to classify"}

    url = f"{settings.classifier_url}/check-text"
    try:
        async with httpx.AsyncClient(timeout=settings.fast_timeout) as client:
            r = await client.post(
                url,
                json={
                    "text": text,
                    # Network fact-check lookups add seconds per request and the
                    # extension runs on every post you scroll past. Off here.
                    "check_facts": False,
                    "resolve_links": False,
                },
            )
            r.raise_for_status()
            data = r.json()
            data["available"] = True
            return data
    except httpx.HTTPStatusError as exc:
        detail = _detail(exc)
        log.warning("Classifier returned %s: %s", exc.response.status_code, detail)
        return {"available": False, "error": detail}
    except Exception as exc:
        log.warning("Classifier unreachable at %s: %s", url, exc)
        return {
            "available": False,
            "error": f"Post checker not reachable on {settings.classifier_url}. "
                     f"Start it, then retry.",
        }


# --------------------------------------------------------------------------- #
# Fake follower / bot account model  (thin wrapper API, port 8002)
# --------------------------------------------------------------------------- #
async def predict_account(features: dict) -> dict:
    """Classify one Instagram account from the 7 raw profile features."""
    url = f"{settings.follower_url}/predict-account"
    try:
        async with httpx.AsyncClient(timeout=settings.fast_timeout) as client:
            r = await client.post(url, json=features)
            r.raise_for_status()
            data = r.json()
            data["available"] = True
            return data
    except httpx.HTTPStatusError as exc:
        detail = _detail(exc)
        log.warning("Account model returned %s: %s", exc.response.status_code, detail)
        return {"available": False, "error": detail}
    except Exception as exc:
        log.warning("Account model unreachable at %s: %s", url, exc)
        return {
            "available": False,
            "error": f"Account model not reachable on {settings.follower_url}.",
        }


# --------------------------------------------------------------------------- #
# Video-to-text transcriber  (D:\video-to-text transcriber, port 8000)
# --------------------------------------------------------------------------- #
async def transcribe_reel(page_url: str, language: str | None = None) -> dict:
    """Transcribe the spoken audio of a reel, given its Instagram page URL.

    Uses the transcriber's /transcribe/url path deliberately: that route goes
    through yt-dlp with the project's verified cookies.txt, which is the one
    Instagram download path already proven to work. It side-steps the blob:
    problem entirely, the page never has to hand over media bytes.

    Submits the job, then polls. Whisper on CPU is roughly realtime, so a 30s
    reel is a ~30s wait; the caller decides whether to make the user wait.
    """
    base = f"{settings.transcriber_url}/api/v1"
    started = time.monotonic()
    set_progress(page_url, state="starting", percent=0,
                 stage="Fetching the video from Instagram…")

    try:
        async with httpx.AsyncClient(timeout=settings.fast_timeout) as client:
            submit = await client.post(
                f"{base}/transcribe/url",
                json={"url": page_url, "language": language, "wait": False},
            )
            submit.raise_for_status()
            job = submit.json()
    except httpx.HTTPStatusError as exc:
        set_progress(page_url, state="failed", stage=_detail(exc))
        return {"available": False, "error": _detail(exc)}
    except Exception as exc:
        log.warning("Transcriber unreachable at %s: %s", base, exc)
        set_progress(page_url, state="failed", stage="Transcriber not running")
        return {
            "available": False,
            "error": f"Transcriber not reachable on {settings.transcriber_url}.",
        }

    # A cache hit comes back already completed, with the result inline.
    if job.get("status") == "completed" and job.get("result"):
        clear_progress(page_url)
        return _shape_transcript(job["result"], cached=True,
                                 seconds=time.monotonic() - started)

    job_id = job.get("job_id")
    if not job_id:
        set_progress(page_url, state="failed", stage="No job id returned")
        return {"available": False, "error": "Transcriber did not return a job id."}

    # ---- poll until the job settles ----
    try:
        async with httpx.AsyncClient(timeout=settings.fast_timeout) as client:
            while time.monotonic() - started < settings.transcribe_timeout:
                await asyncio.sleep(settings.poll_interval)
                r = await client.get(f"{base}/jobs/{job_id}")
                r.raise_for_status()
                state = r.json()

                set_progress(
                    page_url,
                    state="running",
                    percent=round(float(state.get("progress") or 0.0) * 100),
                    stage=state.get("stage") or "working",
                    elapsed=round(time.monotonic() - started),
                )

                if state.get("status") == "completed":
                    clear_progress(page_url)
                    return _shape_transcript(
                        state.get("result") or {}, cached=bool(state.get("cache_hit")),
                        seconds=time.monotonic() - started,
                    )
                if state.get("status") == "failed":
                    err = state.get("error") or "Transcription failed."
                    set_progress(page_url, state="failed", stage=err[:140])
                    return {"available": False, "error": err}
    except Exception as exc:
        set_progress(page_url, state="failed", stage=str(exc)[:140])
        return {"available": False, "error": f"Lost contact with transcriber: {exc}"}

    set_progress(page_url, state="failed", stage="Timed out")
    return {
        "available": False,
        "error": f"Transcription still running after "
                 f"{settings.transcribe_timeout:.0f}s — gave up waiting.",
    }


def _shape_transcript(result: dict, cached: bool, seconds: float) -> dict:
    """Pull the classifier contract out of a finished transcription job.

    `classifier_input` is the transcriber's documented hand-off block; reading it
    (rather than the raw segments) keeps this gateway on the module's public
    contract instead of its internals.
    """
    ci = result.get("classifier_input") or {}
    return {
        "available": True,
        "text": ci.get("text", "") or "",
        "language": ci.get("language"),
        "confidence": ci.get("confidence", 0.0),
        "quality": ci.get("quality", "unknown"),
        "is_reliable": ci.get("is_reliable", False),
        "sources": ci.get("sources", []),
        "char_count": ci.get("char_count", 0),
        "cached": cached,
        "elapsed_seconds": round(seconds, 1),
    }


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
async def _probe(name: str, url: str) -> tuple[str, dict]:
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(url)
            return name, {"up": r.status_code < 500, "status_code": r.status_code}
    except Exception as exc:
        return name, {"up": False, "error": type(exc).__name__}


async def health_report() -> dict:
    """Ask all three modules at once whether they are up."""
    checks = await asyncio.gather(
        _probe("transcriber", f"{settings.transcriber_url}/api/v1/health"),
        _probe("classifier", f"{settings.classifier_url}/health"),
        _probe("account_model", f"{settings.follower_url}/health"),
    )
    return dict(checks)


def _detail(exc: httpx.HTTPStatusError) -> str:
    """Prefer FastAPI's {"detail": ...} message over a bare status line."""
    try:
        body = exc.response.json()
        if isinstance(body, dict) and "detail" in body:
            return str(body["detail"])
    except Exception:
        pass
    return f"HTTP {exc.response.status_code}"
