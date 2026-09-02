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


class Settings:
    # ---- where the three modules are reachable ----
    transcriber_url: str = _clean(os.getenv("TRANSCRIBER_URL", "http://127.0.0.1:8000"))
    classifier_url: str = _clean(os.getenv("CLASSIFIER_URL", "http://127.0.0.1:8001"))
    follower_url: str = _clean(os.getenv("FOLLOWER_URL", "http://127.0.0.1:8002"))

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
    # The classifier and account model answer in <1s; only leave the transcriber
    # a long read budget because Whisper on CPU is slow.
    fast_timeout: float = float(os.getenv("FAST_TIMEOUT", "60"))
    transcribe_timeout: float = float(os.getenv("TRANSCRIBE_TIMEOUT", "900"))
    poll_interval: float = float(os.getenv("POLL_INTERVAL", "1.5"))

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key)


settings = Settings()
