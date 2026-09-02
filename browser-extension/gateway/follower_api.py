"""
A thin REST wrapper around the existing fake-follower model.

The module at D:\\trustlens-fake-follower-detection is a Streamlit app, so its
model is only reachable through a UI. This exposes the same `predict_core`
functions over HTTP without changing that project at all, it imports from it in
place, so retraining there is picked up here with no copying and no drift.

Run:
    uvicorn follower_api:app --reload --port 8002
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Point at the real module directory so we use the trained artifacts in place.
FOLLOWER_DIR = Path(
    os.getenv("FOLLOWER_MODULE_DIR", r"D:\trustlens-fake-follower-detection")
)
if str(FOLLOWER_DIR) not in sys.path:
    sys.path.insert(0, str(FOLLOWER_DIR))

_IMPORT_ERROR: str | None = None
try:
    from predict_core import (  # type: ignore
        load_artifacts, predict_account, verdict_label, username_digit_ratio,
    )
except Exception as exc:                                    # pragma: no cover
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

app = FastAPI(title="TrustLens Fake-Follower API", version="1.0.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

_MODEL = None
_LOAD_ERROR: str | None = _IMPORT_ERROR


def _get_model():
    """Load the XGBoost artifacts once, on first use."""
    global _MODEL, _LOAD_ERROR
    if _MODEL is None and _LOAD_ERROR is None:
        try:
            _MODEL = load_artifacts()          # (model, scaler, thresholds)
        except Exception as exc:
            _LOAD_ERROR = f"{type(exc).__name__}: {exc}"
    return _MODEL


class AccountRequest(BaseModel):
    username: str = ""
    profile_pic: int = 1
    username_digit_ratio: float | None = None
    description_length: int = 0
    private: int = 0
    posts_count: int = 0
    followers_count: int = 0
    follows_count: int = 0


@app.get("/health")
def health():
    model = _get_model()
    return {
        "status": "ok" if model is not None else "degraded",
        "model_loaded": model is not None,
        "module_dir": str(FOLLOWER_DIR),
        "error": _LOAD_ERROR,
        "hint": None if model is not None else
                "Check FOLLOWER_MODULE_DIR and that artifacts/model.pkl exists "
                "(run train_and_save.py in that project).",
    }


@app.post("/predict-account")
def predict(req: AccountRequest):
    bundle = _get_model()
    if bundle is None:
        raise HTTPException(503, f"Fake-follower model unavailable. {_LOAD_ERROR}")

    model, scaler, thresholds = bundle

    ratio = req.username_digit_ratio
    if ratio is None:
        ratio = username_digit_ratio(req.username or "")

    raw = {
        "profile_pic": int(req.profile_pic),
        "username_digit_ratio": float(ratio),
        "description_length": int(req.description_length),
        "private": int(req.private),
        "posts_count": int(req.posts_count),
        "followers_count": int(req.followers_count),
        "follows_count": int(req.follows_count),
    }

    try:
        label, prob_fake, feats = predict_account(raw, model, scaler, thresholds)
    except Exception as exc:
        raise HTTPException(422, f"Prediction failed: {exc}") from exc

    v = verdict_label(prob_fake)
    return {
        "username": req.username,
        "label": int(label),
        "prob_fake": round(float(prob_fake), 4),
        "band": v["band"],                 # real | fake | uncertain
        "verdict": v["text"],
        "confidence": round(float(v["confidence"]), 4),
        "color": v["color"],
        "features_used": raw,
    }
