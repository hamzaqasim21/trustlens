"""
The post checker — the `/check-text` service the gateway expects on port 8001.

WHY THIS FILE EXISTS
--------------------
The gateway was originally written against a separate post-checker project
that was never delivered to this repo, so content checking in the extension
has always been dead. This replaces it by wrapping the misinformation
classifier **that the main TrustLens site already uses** — the fine-tuned
XLM-RoBERTa in `backend/misinfo_classifier/`.

That choice is deliberate. Wiring in a second, different text model would
mean the extension and the website could disagree about the same caption,
which is exactly the inconsistency this project has been avoiding. Same
model, same weights, one answer.

WHAT IS AI HERE AND WHAT IS NOT
-------------------------------
- The **category** (credible / financial_scam / health_misinformation / ...)
  comes from the trained XLM-RoBERTa model. That is genuine machine learning,
  77% accuracy on a held-out test set.
- The **red flags** come from `red_flags.py`, which is hand-written regular
  expressions. That is not AI and must never be described as such.

Both are reported separately on purpose, because `analyzer.py` deliberately
trusts the flags more than the category — see its docstring for the measured
reason why.

Run:
    uvicorn post_checker_api:app --port 8001
"""
from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


# Import the site's own classifier in place rather than copying it, so a
# retrain over there is picked up here with no drift between the two.
def _find_backend_dir() -> Path:
    """Walks up from this file looking for the TrustLens backend, located by a
    file that is actually in it rather than by counting parent directories, so
    moving this folder cannot silently break the import."""
    override = os.getenv("TRUSTLENS_BACKEND_DIR")
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        if (parent / "misinfo_classifier").is_dir():
            return parent
    return Path(__file__).resolve().parents[1]


BACKEND_DIR = _find_backend_dir()
_CLASSIFIER_DIR = BACKEND_DIR / "misinfo_classifier" / "api"
for _p in (str(BACKEND_DIR), str(_CLASSIFIER_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# The red-flag rules live in backend/red_flags.py, shared with the website's
# own scoring, so the extension and the site apply the exact same rules.
from red_flags import detect_red_flags, flag_pressure  # noqa: E402

_IMPORT_ERROR: str | None = None
try:
    # One text at a time and a CPU limit are enforced inside model_loader itself,
    # because the website backend mounts this app and shares the one loaded model
    # (see backend/main.py).
    from model_loader import classify_text, load_model  # type: ignore
except Exception as exc:  # pragma: no cover - only hit on a broken install
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

@asynccontextmanager
async def lifespan(app):
    if not _IMPORT_ERROR:
        # Load the 1.1 GB model now, not on the first reel someone scans.
        await asyncio.to_thread(load_model)
    yield


app = FastAPI(title="TrustLens Post Checker", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# Below this gap between the top two categories, the model is effectively
# guessing between them. analyzer.py uses this to avoid letting a coin-flip
# category drive a badge.
LOW_MARGIN_THRESHOLD = 0.15

# One high-severity flag (weight 3) lands at 36, two at 72. Tuned so that a
# single hard flag is serious without being maximal on its own.
FLAG_LIFT_PER_POINT = 12


class TextRequest(BaseModel):
    text: str
    # Accepted because the gateway sends them, and honoured honestly: this
    # service does no network lookups at all. External fact-checking was
    # deliberately dropped from this project (see CLAUDE.md, "Abandoned:
    # Google Custom Search"), so rather than silently ignoring these, the
    # response states plainly that no lookup was performed.
    check_facts: bool = False
    resolve_links: bool = False


def _model_is_loaded() -> bool:
    try:
        import model_loader  # type: ignore
        return model_loader._model is not None
    except Exception:
        return False


@app.get("/health")
def health():
    return {
        "status": "degraded" if _IMPORT_ERROR else "ok",
        "classifier_importable": _IMPORT_ERROR is None,
        "model_loaded": _model_is_loaded(),
        "backend_dir": str(BACKEND_DIR),
        "error": _IMPORT_ERROR,
    }


@app.post("/check-text")
def check_text(req: TextRequest):
    """Classify a caption or transcript and scan it for scam patterns.

    Never raises on bad input. The gateway treats an error response as "this
    module is down" and degrades the badge honestly, which is the correct
    behaviour — but an empty caption is not an outage, it is just nothing to
    check, so that returns a clean, available result.
    """
    text = (req.text or "").strip()
    flags = detect_red_flags(text)
    pressure = flag_pressure(flags)

    category = "credible"
    category_label = "Credible"
    confidence = 0.0
    classifier_risk = 0
    low_margin = False
    classifier_error = None
    model_result = None

    if _IMPORT_ERROR:
        classifier_error = _IMPORT_ERROR
    elif text:
        result = classify_text(text)
        if result.get("status") == "success":
            model_result = result
            category = result.get("primary_category", "credible")
            category_label = category.replace("_", " ").title()
            confidence = float(result.get("confidence") or 0.0)
            classifier_risk = int(result.get("risk_score") or 0)

            scores = result.get("category_scores") or {}
            if len(scores) >= 2:
                top_two = sorted(scores.values(), reverse=True)[:2]
                low_margin = (top_two[0] - top_two[1]) < LOW_MARGIN_THRESHOLD
        else:
            classifier_error = result.get("error") or "classifier returned no result"

    # The two signals are independent, so the score takes the worse of them
    # rather than averaging. Averaging would let a confidently-clean category
    # dilute a hard scam pattern — which is the specific failure mode
    # analyzer.py documents the classifier having on real caption text.
    flag_lift = min(100, pressure * FLAG_LIFT_PER_POINT)
    post_risk_score = max(classifier_risk, flag_lift)

    return {
        "category": category,
        "category_label": category_label,
        "confidence": round(confidence, 4),
        "post_risk_score": int(post_risk_score),
        "red_flags": flags,
        "low_margin": low_margin,
        # Transparency about which half of the answer actually ran.
        "classifier_available": classifier_error is None and bool(text),
        "classifier_error": classifier_error,
        "classifier_risk_score": classifier_risk,
        # The classifier's own output, unchanged, so the gateway can apply the
        # website's misinfo_assessment.py rules to it exactly as the site does.
        "model_result": model_result,
        "flag_pressure": pressure,
        "fact_check_performed": False,
        "fact_check_note": (
            "This service performs no external fact-check or link resolution; "
            "the score comes from the local classifier and pattern matching only."
        ) if (req.check_facts or req.resolve_links) else None,
    }
