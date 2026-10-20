"""
Instagram data for the extension, fetched through RapidAPI — the same provider
and the same `backend/data_ingestion.py` the TrustLens website uses.

Why the gateway fetches instead of trusting the page:
Instagram's page only shows follower counts on a profile page, hides captions
behind "more", and swaps reels in and out of the DOM as you swipe. Reading any
of that from the page is a guess. The reel's shortcode in the address bar is
not a guess, so the gateway takes it and asks RapidAPI for the real caption,
the real poster, their real profile, and the direct video file.

Every result is cached, so scrolling back to a reel, or seeing the same creator
twice, never spends a second request.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import time
from pathlib import Path

log = logging.getLogger(__name__)


def _find_backend_dir() -> Path:
    override = os.getenv("TRUSTLENS_BACKEND_DIR")
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        if (parent / "data_ingestion.py").exists():
            return parent
    return Path(__file__).resolve().parents[2]


BACKEND_DIR = _find_backend_dir()
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_IMPORT_ERROR: str | None = None
try:
    from data_ingestion import (  # type: ignore
        fetch_engagement_data, fetch_instagram_profile, fetch_media_data)
except Exception as exc:  # pragma: no cover - only hit on a broken install
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

MEDIA_TTL = 6 * 3600       # a post's caption and owner don't change
PROFILE_TTL = 3600         # follower counts drift slowly
FAILURE_TTL = 60           # don't hammer the API for something that just failed

_cache: dict[str, tuple[float, dict]] = {}
_locks: dict[str, asyncio.Lock] = {}

_SHORTCODE = re.compile(r"/(?:p|reel|reels|tv)/([A-Za-z0-9_-]{5,})")


def shortcode_from(url: str) -> str | None:
    m = _SHORTCODE.search(url or "")
    return m.group(1) if m else None


def configured() -> bool:
    return _IMPORT_ERROR is None and bool(os.getenv("RAPIDAPI_KEY"))


def status() -> dict:
    if _IMPORT_ERROR:
        return {"up": False, "error": _IMPORT_ERROR}
    if not os.getenv("RAPIDAPI_KEY"):
        return {"up": False, "error": "RAPIDAPI_KEY missing from backend/.env"}
    return {"up": True, "provider": "RapidAPI (same as the website)"}


async def _cached(key: str, ttl: float, fetch) -> dict:
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]

    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:   # two badges asking for the same reel make one request
        hit = _cache.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        try:
            try:
                data = await asyncio.to_thread(fetch)
            except Exception:
                # RapidAPI occasionally returns an incomplete answer (seen:
                # a profile with no follower count) that is fine a second later.
                await asyncio.sleep(1)
                data = await asyncio.to_thread(fetch)
            result = {"available": True, **data}
            _cache[key] = (time.monotonic() + ttl, result)
        except Exception as exc:
            log.warning("RapidAPI fetch failed for %s: %s", key, exc)
            result = {"available": False, "error": str(exc)}
            _cache[key] = (time.monotonic() + FAILURE_TTL, result)
        return result


async def get_media(code: str) -> dict:
    hit = _cache.get(f"media:{code}")
    if hit and hit[0] > time.monotonic() and hit[1].get("available"):
        return hit[1]   # already known, e.g. read from Instagram's own page data
    if not configured():
        return {"available": False, "error": status().get("error")}
    return await _cached(f"media:{code}", MEDIA_TTL, lambda: fetch_media_data(code))


async def get_profile(username: str) -> dict:
    username = (username or "").strip().lstrip("@").lower()
    if not username:
        return {"available": False, "error": "no username"}
    if not configured():
        return {"available": False, "error": status().get("error")}
    return await _cached(f"profile:{username}", PROFILE_TTL,
                         lambda: fetch_instagram_profile(username))


async def get_engagement(username: str) -> dict:
    """The poster's last 12 posts' likes/comments — the same data and the same
    call the website's scan uses for its Engagement module."""
    username = (username or "").strip().lstrip("@").lower()
    if not username:
        return {"available": False, "error": "no username"}
    if not configured():
        return {"available": False, "error": status().get("error")}
    return await _cached(f"engagement:{username}", PROFILE_TTL,
                         lambda: fetch_engagement_data(username))


def account_features(profile: dict) -> dict:
    """The fake-account model's inputs, from a RapidAPI profile — the exact
    fields the website's own scan feeds the same model."""
    return {
        "username": profile.get("username", ""),
        "full_name": profile.get("full_name", "") or "",
        "profile_pic": 1 if profile.get("has_profile_pic") else 0,
        "description_length": int(profile.get("bio_length") or 0),
        "has_external_url": 1 if profile.get("has_external_url") else 0,
        "private": 1 if profile.get("is_private") else 0,
        "posts_count": int(profile.get("posts") or 0),
        "followers_count": int(profile.get("followers") or 0),
        "follows_count": int(profile.get("following") or 0),
    }


# --------------------------------------------------------------------------- #
# Reel data that Instagram's own page already downloaded
# --------------------------------------------------------------------------- #
# The extension reads the reel data Instagram's page fetches for itself (the
# same fields RapidAPI returns, because RapidAPI reads the same Instagram API).
# Using it skips a ~4-7s RapidAPI round trip for the reel on screen and lets the
# next reels be checked before the viewer reaches them. It comes from a web
# page, so it is treated as untrusted input and cleaned here.
_CODE = re.compile(r"^[A-Za-z0-9_-]{5,40}$")
_USERNAME = re.compile(r"^[A-Za-z0-9._]{1,30}$")
_VIDEO_HOSTS = (".cdninstagram.com", ".fbcdn.net")


def _safe_video_url(url: str) -> str:
    from urllib.parse import urlparse
    try:
        u = urlparse(url or "")
    except ValueError:
        return ""
    host = (u.hostname or "").lower()
    if u.scheme == "https" and host.endswith(_VIDEO_HOSTS):
        return url
    return ""   # never let a page make the gateway fetch an arbitrary address


def _int(v) -> int:
    try:
        return max(0, int(v or 0))
    except (TypeError, ValueError):
        return 0


def clean_page_media(item: dict | None) -> dict | None:
    if not isinstance(item, dict):
        return None
    code = str(item.get("code") or "")
    username = str(item.get("username") or "")
    if not _CODE.match(code) or not _USERNAME.match(username):
        return None
    video_url = _safe_video_url(str(item.get("video_url") or ""))
    return {
        "code": code,
        "caption": str(item.get("caption") or "")[:5000].strip(),
        "username": username,
        "full_name": str(item.get("full_name") or "")[:100],
        "is_verified": bool(item.get("is_verified")),
        "is_private": bool(item.get("is_private")),
        "is_video": bool(video_url) or bool(item.get("is_video")),
        "has_audio": bool(item.get("has_audio", bool(video_url))),
        "video_url": video_url,
        # Audio-only track from Instagram's own streaming manifest, when the
        # page had it: a fraction of the size of the video. Same host check.
        "audio_url": _safe_video_url(str(item.get("audio_url") or "")),
        "like_count": _int(item.get("like_count")),
        "comment_count": _int(item.get("comment_count")),
        "source": "page",
    }


def seed_media(item: dict) -> None:
    """Cache page-provided reel data, so get_media() answers instantly."""
    key = f"media:{item['code']}"
    hit = _cache.get(key)
    if hit and hit[1].get("available") and hit[1].get("source") != "page":
        return   # RapidAPI's copy is already here; keep it
    _cache[key] = (time.monotonic() + MEDIA_TTL, {"available": True, **item})
