"""
model_loader.py
----------------
Loads the fine-tuned XLM-RoBERTa model (from Colab training) and
exposes a single classify_text() function returning the API contract
shape the Trust Score Engine expects.

Classes (must match train_model.py):
    0 -> credible
    1 -> health_misinformation
    2 -> political_propaganda
    3 -> financial_scam
"""

import os
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL_DIR = os.getenv("MODEL_DIR", "./model")
LABEL_NAMES = ["credible", "health_misinformation", "political_propaganda", "financial_scam"]

_device = "cuda" if torch.cuda.is_available() else "cpu"
_tokenizer = None
_model = None


def load_model():
    """Loads tokenizer + model once, on first use (lazy load so the API
    can start even before you've placed the trained model in ./model)."""
    global _tokenizer, _model
    if _model is None:
        if not os.path.isdir(MODEL_DIR):
            raise RuntimeError(
                f"Model directory '{MODEL_DIR}' not found. "
                "Download the trustlens_misinfo_model folder from Colab "
                "and place it here (or set MODEL_DIR env var)."
            )
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
        _model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)
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

    inputs = tokenizer(
        text, truncation=True, padding=True, max_length=256, return_tensors="pt"
    ).to(_device)

    with torch.no_grad():
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
