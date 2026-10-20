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

import httpx

from config import settings

log = logging.getLogger(__name__)

# Live transcription progress, keyed by the reel's page URL.
#
# /analyze blocks while a reel is being listened to, so the badge has no other
# way to learn how far along it is. reel_audio.py reports progress here and the
# extension polls GET /progress, so a wait never looks like a hang.
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
# The same text gets classified again when you return to a reel, and a
# pre-checked reel was already classified in the background. Remember results.
_classify_cache: dict[str, dict] = {}
_account_cache: dict[str, dict] = {}


def _remember(cache: dict, key: str, value: dict) -> dict:
    if value.get("available"):
        if len(cache) > 500:
            cache.pop(next(iter(cache)))
        cache[key] = value
    return value


class _Service:
    """One model service that may be reachable at more than one address.

    Remembers the address that last answered and only moves to another when
    nothing is listening at the current one (connection refused). A slow
    answer is NOT a reason to switch: that service is alive and busy, and
    sending the same text elsewhere would only load a second copy of a 1 GB
    model onto the same laptop."""

    def __init__(self, name: str, urls: list):
        self.name = name
        self.urls = urls
        self.current = urls[0]

    def _order(self) -> list:
        return [self.current] + [u for u in self.urls if u != self.current]

    async def post(self, path: str, payload: dict, timeout: float):
        last_exc = None
        async with httpx.AsyncClient(timeout=timeout) as client:
            for base in self._order():
                try:
                    r = await client.post(f"{base}{path}", json=payload)
                except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                    last_exc = exc
                    continue
                if r.status_code == 404:        # something else lives there
                    last_exc = httpx.HTTPStatusError("404", request=r.request, response=r)
                    continue
                self.current = base
                return r
        raise last_exc or httpx.ConnectError("no address answered")

    async def health(self) -> dict:
        async with httpx.AsyncClient(timeout=8.0) as client:
            for base in self._order():
                try:
                    r = await client.get(f"{base}/health")
                except Exception:
                    continue
                if r.status_code < 400:
                    self.current = base
                    info = {"up": True, "status_code": r.status_code, "via": base}
                    try:
                        body = r.json()
                        if "model_loaded" in body:
                            info["loaded"] = bool(body["model_loaded"])
                    except Exception:
                        pass
                    return info
        return {"up": False, "tried": self._order()}


CLASSIFIER = _Service("classifier", settings.classifier_urls)
ACCOUNT_MODEL = _Service("account_model", settings.follower_urls)


async def classify_text(text: str) -> dict:
    if text and text in _classify_cache:
        return dict(_classify_cache[text])
    return _remember(_classify_cache, text or "", await _classify_text(text))


async def predict_account(features: dict) -> dict:
    key = repr(sorted(features.items()))
    if key in _account_cache:
        return dict(_account_cache[key])
    return _remember(_account_cache, key, await _predict_account(features))


async def _classify_text(text: str) -> dict:
    """Send caption/transcript text to the post checker.

    Returns its full report on success. On failure returns
    {"available": False, "error": ...} rather than raising, so a missing
    classifier degrades the verdict instead of breaking it.
    """
    if not text or not text.strip():
        return {"available": False, "error": "no text to classify"}

    try:
        r = await CLASSIFIER.post("/check-text", {
            "text": text,
            # Network fact-check lookups add seconds per request. Off here.
            "check_facts": False,
            "resolve_links": False,
        }, settings.fast_timeout)
        r.raise_for_status()
        data = r.json()
        data["available"] = True
        return data
    except httpx.HTTPStatusError as exc:
        detail = _detail(exc)
        log.warning("Classifier returned %s: %s", exc.response.status_code, detail)
        return {"available": False, "error": detail}
    except Exception as exc:
        log.warning("Classifier unreachable (%s): %s", ", ".join(CLASSIFIER.urls), exc)
        return {
            "available": False,
            "error": "the misinformation model isn't running (start the services with start_all.ps1)",
        }


# --------------------------------------------------------------------------- #
# Fake follower / bot account model  (thin wrapper API, port 8002)
# --------------------------------------------------------------------------- #
async def _predict_account(features: dict) -> dict:
    """Classify one Instagram account from the 7 raw profile features."""
    try:
        r = await ACCOUNT_MODEL.post("/predict-account", features, settings.fast_timeout)
        r.raise_for_status()
        data = r.json()
        data["available"] = True
        return data
    except httpx.HTTPStatusError as exc:
        detail = _detail(exc)
        log.warning("Account model returned %s: %s", exc.response.status_code, detail)
        return {"available": False, "error": detail}
    except Exception as exc:
        log.warning("Account model unreachable (%s): %s", ", ".join(ACCOUNT_MODEL.urls), exc)
        return {
            "available": False,
            "error": "the fake-account model isn't running (start the services with start_all.ps1)",
        }


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
async def health_report() -> dict:
    """Ask the two model services at once whether they are up."""
    checks = await asyncio.gather(
        CLASSIFIER.health(),
        ACCOUNT_MODEL.health(),
    )
    return {"classifier": checks[0], "account_model": checks[1]}


def _detail(exc: httpx.HTTPStatusError) -> str:
    """Prefer FastAPI's {"detail": ...} message over a bare status line."""
    try:
        body = exc.response.json()
        if isinstance(body, dict) and "detail" in body:
            return str(body["detail"])
    except Exception:
        pass
    return f"HTTP {exc.response.status_code}"
