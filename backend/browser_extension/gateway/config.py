"""
Gateway configuration, all values come from environment / .env, every one has a
working default so an empty .env still runs.

The gateway is the ONLY service the browser extension talks to. It orchestrates
the three existing TrustLens modules (each already running on its own port) plus
Gemini for the plain-English "Why?" explanations, and it is the only place the
Gemini key ever lives, never the extension.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env sitting next to this file (if present). Real environment variables
# still win over the file, which is what you want in production.
load_dotenv(Path(__file__).parent / ".env")


def _clean(url: str) -> str:
    return (url or "").rstrip("/")


def _urls(configured: str, defaults: list) -> list:
    out = []
    for u in [*(configured or "").split(","), *defaults]:
        u = _clean(u.strip())
        if u and u not in out:
            out.append(u)
    return out


class Settings:
    # ---- where the two model services are reachable ----
    # First choice: inside the TrustLens website backend (port 8000), which
    # mounts both services and shares its one loaded copy of each model with
    # them. Fallback: the old standalone services on 8001 / 8002. A URL set in
    # .env is tried first; the defaults are always kept as fallbacks, so an
    # older .env that still says 8001 keeps working.
    classifier_urls: list = _urls(os.getenv("CLASSIFIER_URL", ""),
                                  ["http://127.0.0.1:8000/ext/classifier", "http://127.0.0.1:8001"])
    follower_urls: list = _urls(os.getenv("FOLLOWER_URL", ""),
                                ["http://127.0.0.1:8000/ext/account", "http://127.0.0.1:8002"])

    # ---- Gemini (free tier via Google AI Studio) ----
    # Get a free key at https://aistudio.google.com/apikey and put it in .env.
    # If left blank, the "Why?" button falls back to a rule-based explanation
    # built from the red flags, the rest of the pipeline still works.
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    # Verified working on this key. Avoid the moving aliases
    # (`gemini-flash-latest`): one was measured ignoring thinkingBudget=0 and
    # returning truncated output, and an alias can change behaviour under you
    # without the code changing at all.
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

    # ---- this gateway ----
    host: str = os.getenv("GATEWAY_HOST", "127.0.0.1")
    port: int = int(os.getenv("GATEWAY_PORT", "8100"))

    # ---- timeouts (seconds) ----
    # The classifier and account model answer in under a second.
    fast_timeout: float = float(os.getenv("FAST_TIMEOUT", "60"))
    poll_interval: float = float(os.getenv("POLL_INTERVAL", "1.5"))

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key)


settings = Settings()
