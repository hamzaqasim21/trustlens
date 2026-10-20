"""
TrustLens Gateway, the single service the browser extension talks to.

Why this exists rather than the extension calling the modules directly:

- **Keys stay on this machine.** The Gemini and RapidAPI keys never ship inside
  the extension, whose source every user can read.
- **One contract.** The extension says which post is on screen and gets one
  verdict back. Modules can move or change port without touching the extension.
- **The same models as the website.** The classifier and account model are the
  website's own (wrapped by post_checker_api.py and follower_api.py), and the
  Instagram data comes from the same RapidAPI provider via data_ingestion.py.

Run:
    uvicorn main:app --port 8100
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import clients
import instagram_data
import reel_audio
import scoring
from analyzer import build_verdict
from config import settings
from explain import explain as build_explanation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gateway")

@asynccontextmanager
async def lifespan(app):
    # Load the speech model in the background, so the first reel you stop on
    # doesn't also wait for a model load.
    asyncio.get_running_loop().run_in_executor(None, reel_audio.warm_up)
    yield


app = FastAPI(
    title="TrustLens Gateway",
    description="Orchestrates the TrustLens modules for the live Instagram extension.",
    version="2.0.0",
    lifespan=lifespan,
)

# Calls normally arrive from the extension's background worker
# (chrome-extension:// origin). "*" is acceptable because this binds to
# 127.0.0.1 and holds no user data; narrow it if this is ever deployed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Request models — what the content script sends
# --------------------------------------------------------------------------- #
class AccountFeatures(BaseModel):
    """Profile stats, either read off an open profile page or from RapidAPI."""
    username: str = ""
    full_name: str = ""
    has_external_url: int = 0
    profile_pic: int = 1
    username_digit_ratio: float | None = None   # derived from username if omitted
    description_length: int = 0
    private: int = 0
    posts_count: int = 0
    followers_count: int = 0
    follows_count: int = 0


class AnalyzeRequest(BaseModel):
    page_url: str = Field("", description="URL of the post/reel/profile being viewed")
    caption: str = Field("", description="Caption read from the page (fallback only)")
    on_screen_text: str = Field("", description="Image alt-text read from the page")
    is_reel: bool = Field(False, description="The page thinks this is a video")
    username: str = Field("", description="Author read from the page (fallback only)")
    transcribe: bool = Field(
        False,
        description="Listen to the reel's audio (Whisper). A few seconds for a "
                    "short reel; the extension asks once you stop on a reel.",
    )
    listen: bool = Field(
        False,
        description="Start listening to the reel's audio in the background as soon "
                    "as its video is known, without waiting for it. A follow-up call "
                    "with transcribe=true then picks up the running job.",
    )
    account: AccountFeatures | None = None
    media: dict | None = Field(
        None,
        description="The reel's data as Instagram's own page already loaded it "
                    "(caption, poster, video). Saves a RapidAPI round trip.",
    )
    enrich: bool = Field(
        True,
        description="Fetch the real caption, poster and profile through RapidAPI. "
                    "Cached per post and per account, so a repeat costs nothing.",
    )


class PrefetchRequest(BaseModel):
    items: list[dict] = Field(default_factory=list, description="Upcoming reels")
    listen: bool = True


class WarmRequest(BaseModel):
    page_url: str = ""
    username: str = ""
    media: dict | None = None


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
    modules["transcriber"] = reel_audio.status()
    modules["instagram_data"] = instagram_data.status()
    return {
        "status": "ok",
        "gateway": True,
        "gemini_configured": settings.gemini_enabled,
        "modules": modules,
        "hint": "Any module showing up:false only disables its part of the verdict; "
                "the rest still works.",
    }


# Background listening jobs, one per reel, so the first call can start the
# audio while the second call just waits for the same job.
_listen_jobs: dict[str, asyncio.Task] = {}
_background: set[asyncio.Task] = set()
# What /analyze is doing right now, per page, for the badge's live status line.
_stages: dict[str, str] = {}


def _stage(page_url: str, text: str) -> None:
    if page_url:
        _stages[page_url] = text


def _listen_urls(media: dict) -> list:
    """What to listen to: the audio-only track when Instagram's page gave us
    one (a fraction of the download), then the video file as a fallback."""
    return [u for u in (media.get("audio_url"), media.get("video_url")) if u]


def _start_listening(code: str, video_url, page_url: str,
                     on_screen: bool = True) -> asyncio.Task:
    job = _listen_jobs.get(code)
    if job is None:
        job = asyncio.create_task(_listen(code, video_url, page_url, on_screen))
        _listen_jobs[code] = job
        job.add_done_callback(lambda _j, c=code: _listen_jobs.pop(c, None))
    elif on_screen:
        reel_audio.promote(code)   # a pre-check the viewer has now reached
    return job


async def _listen_on_screen(code: str, video_url, page_url: str) -> dict:
    result = await _start_listening(code, video_url, page_url)
    err = result.get("error") or ""
    if not result.get("available") and ("skipped" in err or "in time" in err):
        # Either a pre-check that gave way to another reel, or a download that
        # hit this network's occasional first-connection stall. The reel is on
        # screen now, so run it (once more) for real.
        _listen_jobs.pop(code, None)
        result = await _start_listening(code, video_url, page_url)
    return result


@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    """Everything known about the post in view in, one verdict out."""
    try:
        return await _analyze(req)
    finally:
        _stages.pop(req.page_url, None)


async def _analyze(req: AnalyzeRequest):
    started = time.monotonic()
    timings: dict[str, float] = {}
    code = instagram_data.shortcode_from(req.page_url)

    page_media = instagram_data.clean_page_media(req.media)
    if page_media and page_media["code"] == code:
        instagram_data.seed_media(page_media)
    _stage(req.page_url, "Fetching this reel from Instagram…" if req.is_reel
           else "Fetching this post from Instagram…")

    # ---- 1. The post itself, from RapidAPI rather than guessed from the page ---- #
    # Each RapidAPI call takes ~6s. When the page already told us who posted
    # this, fetch their profile at the same time as the post instead of after.
    hint = (req.username or "").strip().lstrip("@").lower()
    profile_prefetch = None
    if hint and req.enrich and req.account is None:
        profile_prefetch = asyncio.create_task(instagram_data.get_profile(hint))

    media: dict = {"available": False, "error": "no post id in this URL"}
    if code and req.enrich:
        t0 = time.monotonic()
        media = await instagram_data.get_media(code)
        timings["reel_data"] = round(time.monotonic() - t0, 2)
    have_media = bool(media.get("available"))

    caption = req.caption.strip()
    caption_source = "page"
    if have_media and media.get("caption"):
        caption = media["caption"]
        caption_source = "instagram"
    author = (media.get("username") if have_media else "") \
        or req.username or (req.account.username if req.account else "")
    is_reel = bool(media.get("is_video")) if have_media else req.is_reel

    # Start listening now, so it overlaps the account check below instead of
    # waiting for it (the first reel you open used to do these one after another).
    if (is_reel and (req.listen or req.transcribe) and have_media
            and media.get("video_url") and media.get("has_audio")
            and reel_audio.cached(code) is None):
        _start_listening(code, _listen_urls(media), req.page_url)

    # ---- 2. The account that posted it ---- #
    profile: dict = {"available": False}
    eng_task = None
    if author and req.enrich:
        eng_task = asyncio.create_task(instagram_data.get_engagement(author))
    account_task = None
    account_source = None
    page_account = req.account is not None and (
        not author or req.account.username.lower() == author.lower())
    if page_account:
        account_task = asyncio.create_task(
            clients.predict_account(_account_payload(req.account)))
        account_source = "page"
    elif author and req.enrich:
        _stage(req.page_url, f"Checking @{author}'s account…")
        t0 = time.monotonic()
        if profile_prefetch is not None and author.lower() == hint:
            profile = await profile_prefetch
        else:
            profile = await instagram_data.get_profile(author)
        timings["account_data"] = round(time.monotonic() - t0, 2)
        if profile.get("available"):
            features = AccountFeatures(**instagram_data.account_features(profile))
            account_task = asyncio.create_task(
                clients.predict_account(_account_payload(features)))
            account_source = "instagram"

    # ---- 3. What the reel says out loud ---- #
    transcript: dict = {}
    if is_reel:
        heard = reel_audio.cached(code) if code else None
        if heard is not None:
            transcript = heard
        elif have_media and not media.get("has_audio"):
            transcript = {"available": True, "text": "", "no_speech": True,
                          "no_audio": True, "quality": "none", "is_reliable": False}
        elif (req.transcribe or req.listen) and have_media and media.get("video_url"):
            if req.transcribe:
                t0 = time.monotonic()
                transcript = await _listen_on_screen(code, _listen_urls(media), req.page_url)
                timings["listening"] = round(time.monotonic() - t0, 2)
            else:
                _start_listening(code, _listen_urls(media), req.page_url)
                transcript = {"available": False, "in_progress": True,
                              "error": "listening now"}
        elif req.transcribe:
            transcript = {"available": False,
                          "error": media.get("error") or "no video file for this reel"}
        else:
            transcript = {"available": False, "error": "not listened to yet"}

    # ---- 4. Judge the words: caption, alt-text, speech, and the poster's bio ---- #
    parts: list[str] = []
    sources: list[str] = []
    if caption:
        parts.append(caption)
        sources.append("caption")
    if req.on_screen_text.strip():
        parts.append(req.on_screen_text.strip())
        sources.append("on_screen_text")
    heard_text = (transcript.get("text") or "").strip() if transcript.get("available") else ""
    if heard_text and transcript.get("is_reliable"):
        parts.append(heard_text)
        sources.append("speech")
    elif heard_text:
        # Measured: on a music/crowd reel the speech model "heard" words it was
        # only 28% sure of the language of, and those invented words were then
        # scored as political content. Unclear speech is shown, never scored.
        transcript["not_counted"] = True
    bio = (profile.get("biography") or "").strip() if profile.get("available") else ""
    if bio:
        parts.append(bio)
        sources.append("bio")
    text_used = "\n\n".join(parts).strip()

    _stage(req.page_url, "Reading the caption…")
    t0 = time.monotonic()
    # Each text is read on its own — exactly how the website judges a bio and
    # each caption — and the red-flag badge is built from those same results.
    # (It used to also send every text glued together as one more read: extra
    # load on the model, and the model only reads ~384 words, so the glued
    # version was cut short anyway.) The model runs one text at a time, so
    # these go one after another rather than piling up at once.
    per_source = list(zip(sources, parts))
    results = [await clients.classify_text(t) for _, t in per_source]
    texts_checked = [(src, t, r) for (src, t), r in zip(per_source, results)]
    classification = _combine(results)
    timings["models"] = round(time.monotonic() - t0, 2)
    if account_task is not None:
        account = await account_task
    elif author and req.enrich:
        account = {"available": False,
                   "error": profile.get("error") or "couldn't fetch this account"}
    else:
        account = {"available": False, "error": "couldn't tell who posted this"}

    verdict = build_verdict(classification, account, transcript, text_used, sources,
                            is_reel=is_reel)
    verdict["page_url"] = req.page_url
    verdict["elapsed_seconds"] = round(time.monotonic() - started, 1)
    verdict["timings"] = timings
    if transcript:
        verdict["transcript"] = transcript
    eng = await eng_task if eng_task is not None else {"available": False}
    cred = await asyncio.to_thread(scoring.credential, profile)
    _apply_trust_score(verdict, account, profile, eng, texts_checked, cred)

    verdict["coverage"]["listening"] = bool(transcript.get("in_progress"))
    verdict["coverage"]["can_listen"] = bool(
        is_reel and have_media and media.get("video_url")
        and not transcript.get("available"))

    # What the badge shows about the post and its author.
    verdict["post"] = {
        "code": code,
        "author": author or None,
        "caption_source": caption_source if caption else None,
        "data_source": ("instagram_page" if media.get("source") == "page" else "rapidapi")
                       if have_media else None,
        "likes": media.get("like_count") if have_media else None,
        "comments": media.get("comment_count") if have_media else None,
        "data_error": None if (have_media or not code) else media.get("error"),
    }
    if account.get("available"):
        from_api = bool(profile.get("available"))
        acct = req.account
        verdict["account"].update({
            "username": author or account.get("username"),
            "source": account_source,
            "followers": profile.get("followers") if from_api else (acct.followers_count if acct else None),
            "following": profile.get("following") if from_api else (acct.follows_count if acct else None),
            "posts": profile.get("posts") if from_api else (acct.posts_count if acct else None),
            "is_verified": bool(profile.get("is_verified")) if from_api else None,
            "verdict": account.get("verdict"),
        })

    log.info("analyze %s @%s -> %s %s (%s) in %.1fs [%s]", code, author or "?",
             verdict["level"], verdict.get("score"), verdict["headline"],
             verdict["elapsed_seconds"], ", ".join(sources) or "no text")
    return verdict


def _combine(results: list) -> dict:
    """One classification for the red-flag badge, from the per-text results:
    the riskiest text's category, and every red flag found in any of them."""
    ok = [r for r in results if r.get("available")]
    if not ok:
        return results[0] if results else {"available": False, "error": "no text to classify"}
    worst = max(ok, key=lambda r: r.get("post_risk_score") or 0)
    flags, seen = [], set()
    for r in ok:
        for f in r.get("red_flags") or []:
            key = (f.get("type"), f.get("detail"))
            if key not in seen:
                seen.add(key)
                flags.append(f)
    return {**worst, "red_flags": flags}


def _apply_trust_score(verdict: dict, account: dict, profile: dict, eng: dict,
                       texts_checked: list, cred: dict | None = None) -> None:
    """Replace the badge's number with the website's Trust Score engine."""
    if verdict["coverage"].get("partial"):
        return   # a reel whose audio hasn't been heard yet gets no number yet
    misinfo = scoring.misinformation(texts_checked)
    ts = scoring.trust_score(account, profile, eng, misinfo, verdict["level"], cred)
    if cred and cred.get("claims_found"):
        verdict["credential"] = cred
    if ts is None:
        # The account couldn't be checked, so the website's engine can't run.
        # Show the content module's own score, labelled as such, or nothing —
        # never the old fixed band.
        if misinfo is not None:
            content = 100 - float(misinfo.get("risk_score") or 0)
            cap = scoring._CAP.get(verdict["level"])
            if cap is not None:
                content = min(content, cap)
            verdict["score"] = int(round(content))
            verdict["score_label"] = "Content only"
            verdict["score_breakdown"] = [{"module": "misinformation",
                                           "label": scoring.MODULE_LABELS["misinformation"],
                                           "score": verdict["score"], "weight": 100.0}]
        else:
            verdict["score"] = None
            verdict["score_label"] = "Not scored"
        return
    before = verdict["level"]
    verdict["level"] = ts["level"]
    verdict["score"] = int(round(ts["score"]))
    verdict["score_label"] = ts["verdict"]
    verdict["trust_score"] = ts
    verdict["score_breakdown"] = [
        {"module": m, "label": scoring.MODULE_LABELS[m],
         "score": round(ts["module_scores"][m]), "weight": ts["weights_used"][m]}
        for m in ts["module_scores"]
    ]
    if ts["capped_by_content"]:
        verdict["reasons"].insert(0, "Score held down because this post itself contains "
                                     "high-risk scam patterns.")
    elif ts["level"] != before and ts["level"] != "clean":
        weakest = min(verdict["score_breakdown"], key=lambda b: b["score"])
        verdict["headline"] = f"{ts['verdict']}: weak {weakest['label'].lower()}"
        verdict["reasons"].insert(0, f"{weakest['label']} scored {weakest['score']}/100, "
                                     f"which pulls the Trust Score down.")
    elif before == "unknown" and ts["level"] == "clean":
        verdict["headline"] = "Nothing suspicious found"
    eng_result = ts.get("engagement")
    if eng_result and eng_result.get("engagement_rate") is not None:
        verdict["account"]["engagement_rate"] = eng_result["engagement_rate"]
        verdict["account"]["engagement_status"] = eng_result["status"]


async def _listen(code: str, video_url, page_url: str, on_screen: bool = True) -> dict:
    clients.set_progress(page_url, state="running", percent=0, stage="Starting…", elapsed=0)
    t0 = time.monotonic()

    def progress(pct: int, stage: str) -> None:
        clients.set_progress(page_url, state="running", percent=pct, stage=stage,
                             elapsed=round(time.monotonic() - t0))

    try:
        return await asyncio.to_thread(reel_audio.transcribe, code, video_url, progress,
                                       on_screen)
    finally:
        clients.clear_progress(page_url)


@app.post("/warm")
async def warm(req: WarmRequest):
    """Get a reel ready to scan without scanning it: remember its data and
    fetch its poster's profile and recent-post engagement. Network only — no
    model runs, nothing is listened to. The extension calls this when you've
    stayed on a reel for a couple of seconds, so if you then press "Scan this
    reel" the answer is almost immediate. Returns at once."""
    code = instagram_data.shortcode_from(req.page_url)
    item = instagram_data.clean_page_media(req.media)
    if item and item["code"] == code:
        instagram_data.seed_media(item)

    async def run():
        author = (req.username or "").strip().lstrip("@")
        if code:
            media = await instagram_data.get_media(code)
            if media.get("available"):
                author = media.get("username") or author
        if author:
            await asyncio.gather(instagram_data.get_profile(author),
                                 instagram_data.get_engagement(author))

    task = asyncio.create_task(run())
    _background.add(task)
    task.add_done_callback(_background.discard)
    return {"warming": code}


@app.post("/prefetch")
async def prefetch(req: PrefetchRequest):
    """Check the next reels before the viewer reaches them: remember their data,
    fetch their poster's profile, and start listening in the background. When
    the viewer swipes to one, /analyze finds everything ready."""
    accepted = []
    for raw in req.items[:4]:
        item = instagram_data.clean_page_media(raw)
        if not item:
            continue
        instagram_data.seed_media(item)
        accepted.append(item["code"])
        for fetch in (instagram_data.get_profile, instagram_data.get_engagement):
            task = asyncio.create_task(fetch(item["username"]))
            _background.add(task)                 # keep a reference until it finishes
            task.add_done_callback(_background.discard)
        if (req.listen and item["video_url"] and item["has_audio"]
                and reel_audio.cached(item["code"]) is None):
            job = _start_listening(item["code"], _listen_urls(item),
                                   f"https://www.instagram.com/reels/{item['code']}/",
                                   on_screen=False)
            # Once heard, run the models too, so arriving at this reel is instant.
            job.add_done_callback(lambda _j, it=item: _warm(it))
    return {"accepted": accepted}


def _warm(item: dict) -> None:
    async def run():
        try:
            await _analyze(AnalyzeRequest(
                page_url=f"https://www.instagram.com/reels/{item['code']}/",
                is_reel=True, media=item))
        except Exception as exc:   # a failed warm-up only costs speed
            log.info("pre-check of %s not finished: %s", item["code"], exc)
    task = asyncio.create_task(run())
    _background.add(task)
    task.add_done_callback(_background.discard)


@app.get("/progress")
async def progress(page_url: str):
    """What is happening for this page right now, polled by the badge: the
    listening progress if audio is being transcribed, else the current step."""
    p = clients.get_progress(page_url)
    if p.get("state", "idle") != "idle":
        return p
    if page_url in _stages:
        return {"state": "running", "stage": _stages[page_url]}
    return p


@app.post("/explain")
async def explain_endpoint(req: ExplainRequest):
    """The 'Why?' button. Separate from /analyze so the badge appears at once and
    Gemini is only called when the user actually asks."""
    return await build_explanation(req.verdict)


def _account_payload(acct: AccountFeatures) -> dict:
    """Fill in the one feature the page does not state directly."""
    ratio = acct.username_digit_ratio
    if ratio is None:
        name = acct.username or ""
        ratio = (sum(c.isdigit() for c in name) / len(name)) if name else 0.0

    return {
        "username": acct.username,
        "full_name": acct.full_name,
        "has_external_url": int(acct.has_external_url),
        "profile_pic": int(acct.profile_pic),
        "username_digit_ratio": float(ratio),
        "description_length": int(acct.description_length),
        "private": int(acct.private),
        "posts_count": int(acct.posts_count),
        "followers_count": int(acct.followers_count),
        "follows_count": int(acct.follows_count),
    }
