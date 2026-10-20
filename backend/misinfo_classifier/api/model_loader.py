"""
model_loader.py
----------------
Loads the fine-tuned XLM-RoBERTa misinformation classifier and
exposes classify_text() returning the shape the Trust Score Engine
expects.

Classes (must match train_model.py):
    0 -> credible
    1 -> health_misinformation
    2 -> political_propaganda
    3 -> financial_scam
    4 -> sensational_clickbait
    5 -> urdu_misinformation
"""

import os
import threading

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL_DIR = os.getenv("MISINFO_MODEL_DIR", os.path.join(os.path.dirname(__file__), "model"))

LABEL_NAMES = [
    "credible",
    "health_misinformation",
    "political_propaganda",
    "financial_scam",
    "sensational_clickbait",
    "urdu_misinformation",
]

_device = "cuda" if torch.cuda.is_available() else "cpu"
_tokenizer = None
_model = None

# One text at a time, and a couple of CPU cores left free. Measured
# 2026-09-28: with several texts classified at once (the extension does
# this while you scroll) this model's memory grew from 2.7 GB to 3.3 GB and
# never came back down; on a friend's 8 GB laptop that ran Windows out of
# memory after a few reels. On a CPU each text already uses every core, so
# running them together was never faster — only bigger. The website and the
# browser extension share this one loaded model (see main.py), so the lock
# covers both.
_load_lock = threading.Lock()
_infer_lock = threading.Lock()
if _device == "cpu":
    torch.set_num_threads(max(2, min(4, (os.cpu_count() or 4) - 2)))


def load_model():
    global _tokenizer, _model
    with _load_lock:
        return _load_model_locked()


def _load_model_locked():
    global _tokenizer, _model
    if _model is None:
        if not os.path.isdir(MODEL_DIR):
            raise RuntimeError(
                f"Model directory '{MODEL_DIR}' not found. "
                "Make sure the trained model files are placed in api/model/."
            )
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
        # low_cpu_mem_usage loads the weights straight into the model instead
        # of building the model and then copying a second full set of weights
        # in — same numbers, without briefly needing twice the 1.1 GB.
        _model = AutoModelForSequenceClassification.from_pretrained(
            MODEL_DIR, low_cpu_mem_usage=True)
        _model.to(_device)
        _model.eval()
    return _tokenizer, _model


def classify_text(text: str) -> dict:
    """
    Classifies a single piece of text (caption or transcript) and
    returns the response shape the Trust Score Engine consumes.
    """
    if not text or not text.strip():
        return {
            "status": "error",
            "error": "empty_text",
            "message": "No text provided to classify.",
        }

    tokenizer, model = load_model()
    with _infer_lock:
        inputs = tokenizer(
            text, truncation=True, padding=True, max_length=384, return_tensors="pt"
        ).to(_device)

        with torch.inference_mode():
            logits = model(**inputs).logits
            probs = F.softmax(logits, dim=-1).squeeze().cpu().tolist()

    category_scores = {name: round(p, 4) for name, p in zip(LABEL_NAMES, probs)}
    pred_idx = int(torch.tensor(probs).argmax())
    primary_category = LABEL_NAMES[pred_idx]
    confidence = round(probs[pred_idx], 4)
    credible_prob = category_scores["credible"]
    risk_score = round(100 * (1 - credible_prob))

    return {
        "status": "success",
        "input_type": "caption",
        "misinformation_flag": primary_category != "credible",
        "primary_category": primary_category,
        "confidence": confidence,
        "category_scores": category_scores,
        "risk_score": risk_score,
    }