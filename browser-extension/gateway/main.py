"""
TrustLens Gateway, the single service the browser extension talks to.

Why this exists rather than the extension calling the three modules directly:

- **The Gemini key stays on this machine.** An extension ships its source to
  every user; a key inside it is a published key.
- **One contract.** The extension sends what it scraped off the page and gets one
  verdict back. Modules can move, change port, or be swapped without touching the
  extension.
- **The modules stay independent.** Nothing here modifies them; it only calls
  their documented endpoints, so each still runs and demos standalone.

Run:
    uvicorn main:app --reload --port 8100
"""
from __future__ import annotations

import asyncio
import logging
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import clients
from analyzer import build_verdict
from config import settings
from explain import explain as build_explanation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gateway")

app = FastAPI(
    title="TrustLens Gateway",
    description="Orchestrates the TrustLens modules for the live Instagram extension.",
    version="1.0.0",
)

# The extension's content script runs with the page's origin (instagram.com), so
# its fetches are cross-origin to this localhost service. Chrome extensions are
# also allowed to call it from a chrome-extension:// origin. Both need CORS.
# This service binds to 127.0.0.1 and holds no user data, so "*" is acceptable
# here, but it must be narrowed if this is ever deployed off localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Request models, this is exactly what the content script scrapes
# --------------------------------------------------------------------------- #
class AccountFeatures(BaseModel):
    """The 7 raw attributes the fake-follower model needs."""
    username: str = ""
    profile_pic: int = 1
    username_digit_ratio: float | None = None   # derived from username if omitted
    description_length: int = 0
    private: int = 0
    posts_count: int = 0
    followers_count: int = 0
    follows_count: int = 0


class AnalyzeRequest(BaseModel):
    page_url: str = Field("", description="URL of the post/reel/profile being viewed")
    caption: str = Field("", description="Caption text scraped from the DOM")
    on_screen_text: str = Field("", description="Any other visible text from the post")
    is_reel: bool = Field(False, description="True when a video/reel is open")
    transcribe: bool = Field(
        False,
        description="Transcribe the reel's spoken audio. Slow on CPU (~realtime), "
                    "so the extension asks for it explicitly.",
    )
    language: str | None = None
    account: AccountFeatures | None = None


class ExplainRequest(BaseModel):
    """Send back the verdict object exactly as it was received."""
    verdict: dict


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/")
def home():
    return {
        "service": "TrustLens Gateway",
        "analyze": "POST /analyze",
        "explain": "POST /explain",
        "health": "GET /health",
        "gemini": "configured" if settings.gemini_enabled else "not configured "
                  "(explanations fall back to rule-based text)",
    }


@app.get("/health")
async def health():
    modules = await clients.health_report()
    return {
        "status": "ok",
        "gateway": True,
        "gemini_configured": settings.gemini_enabled,
        "modules": modules,
        "hint": "Any module showing up:false only disables its part of the verdict; "
                "the rest still works.",
    }


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    """The main call. Everything the extension knows in, one verdict out."""
    started = time.monotonic()

    # ---- decide what text we are judging -------------------------------- #
    parts: list[str] = []
    sources: list[str] = []
    if req.caption.strip():
        parts.append(req.caption.strip())
        sources.append("caption")
    if req.on_screen_text.strip():
        parts.append(req.on_screen_text.strip())
        sources.append("on_screen_text")

    # ---- kick off the slow work first ----------------------------------- #
    # Transcription is the long pole (Whisper on CPU ~realtime), so start it
    # before anything else and let the fast calls overlap with it.
    transcript_task = None
    if req.is_reel and req.transcribe and req.page_url:
        transcript_task = asyncio.create_task(
            clients.transcribe_reel(req.page_url, req.language)
        )

    account_task = None
    if req.account is not None:
        account_task = asyncio.create_task(
            clients.predict_account(_account_payload(req.account))
        )

    transcript: dict = {}
    if transcript_task is not None:
        transcript = await transcript_task
        if transcript.get("available") and transcript.get("text", "").strip():
            parts.append(transcript["text"].strip())
            sources.append("speech")
    elif req.is_reel:
        # A reel we did not listen to is unchecked, not clean. Saying so is the
        # difference between "we found nothing" and "we did not look" — and a
        # scam pitched only in the audio lives exactly in that gap.
        transcript = {
            "available": False,
            "error": "not transcribed — use the 'Listen to audio' button on the badge",
        }

    text_used = "\n\n".join(parts).strip()

    # The classifier runs last because it needs the transcript merged in.
    classification = await clients.classify_text(text_used)
    account = await account_task if account_task is not None else {
        "available": False, "error": "no profile data was visible on this page",
    }

    verdict = build_verdict(classification, account, transcript, text_used, sources,
                            is_reel=req.is_reel)
    verdict["page_url"] = req.page_url
    verdict["elapsed_seconds"] = round(time.monotonic() - started, 1)
    if transcript:
        verdict["transcript"] = transcript

    log.info("analyze -> %s (%s) in %.1fs [%s]",
             verdict["level"], verdict["headline"], verdict["elapsed_seconds"],
             ", ".join(sources) or "no text")
    return verdict


@app.get("/progress")
async def progress(page_url: str):
    """Where a running transcription has got to.

    Polled by the badge while /analyze is blocked. A six-minute wait with no
    feedback is indistinguishable from a hang, this is what makes it legible.
    """
    return clients.get_progress(page_url)


@app.post("/explain")
async def explain_endpoint(req: ExplainRequest):
    """The 'Why?' button. Kept separate from /analyze on purpose: the badge should
    appear immediately, and the explanation only costs a Gemini call when the user
    actually asks for one."""
    result = await build_explanation(req.verdict)
    return result


def _account_payload(acct: AccountFeatures) -> dict:
    """Fill in the one feature the page does not state directly."""
    ratio = acct.username_digit_ratio
    if ratio is None:
        name = acct.username or ""
        ratio = (sum(c.isdigit() for c in name) / len(name)) if name else 0.0

    return {
        "username": acct.username,
        "profile_pic": int(acct.profile_pic),
        "username_digit_ratio": float(ratio),
        "description_length": int(acct.description_length),
        "private": int(acct.private),
        "posts_count": int(acct.posts_count),
        "followers_count": int(acct.followers_count),
        "follows_count": int(acct.follows_count),
    }
