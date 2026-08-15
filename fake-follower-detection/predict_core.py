"""
Shared feature engineering and model loading.

Training and prediction both import from here so the same transforms run in
both places. Mirrors feature_engineering.py.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

ARTIFACT_DIR = Path(__file__).parent / "artifacts"

# Raw attributes available for any public profile
RAW_FEATURES = [
    "profile_pic",           # 1 if the account has a profile picture, else 0
    "username_digit_ratio",  # digits in username / username length
    "description_length",    # number of characters in the bio
    "private",               # 1 if the account is private, else 0
    "posts_count",           # total posts
    "followers_count",       # total followers
    "follows_count",         # total accounts it follows
]

# Engineered features the models are trained on (order matters)
FEATURE_COLS = [
    "profile_pic", "username_digit_ratio", "description_length", "private",
    "posts_count", "followers_count", "follows_count",
    "log_followers", "log_follows", "log_posts",
    "followers_per_post", "follows_to_followers", "engagement_ratio",
    "social_reach", "has_no_posts", "has_many_follows",
    "has_many_followers", "follow_activity_score",
]

# Display labels
RAW_LABELS = {
    "profile_pic": "Has profile picture",
    "username_digit_ratio": "Digits-in-username ratio",
    "description_length": "Bio length (chars)",
    "private": "Private account",
    "posts_count": "Posts",
    "followers_count": "Followers",
    "follows_count": "Following",
}


def add_row_wise_features(data: pd.DataFrame) -> pd.DataFrame:
    """Row-wise transforms, safe on a single row."""
    data = data.copy()
    data["log_followers"] = np.log1p(data["followers_count"])
    data["log_follows"] = np.log1p(data["follows_count"])
    data["log_posts"] = np.log1p(data["posts_count"])
    data["followers_per_post"] = data["followers_count"] / (data["posts_count"] + 1)
    data["follows_to_followers"] = data["follows_count"] / (data["followers_count"] + 1)
    data["engagement_ratio"] = data["posts_count"] / (data["followers_count"] + data["follows_count"] + 1)
    data["social_reach"] = data["followers_count"] / (data["followers_count"] + data["follows_count"] + 1)
    data["has_no_posts"] = (data["posts_count"] == 0).astype(int)
    return data


def add_threshold_features(data: pd.DataFrame,
                           follows_threshold: float,
                           followers_threshold: float) -> pd.DataFrame:
    """Threshold features. Thresholds are the training-set 90th percentiles."""
    data = data.copy()
    data["has_many_follows"] = (data["follows_count"] > follows_threshold).astype(int)
    data["has_many_followers"] = (data["followers_count"] > followers_threshold).astype(int)
    data["follow_activity_score"] = (
        data["has_no_posts"]
        + data["has_many_follows"]
        + (data["follows_to_followers"] > 1).astype(int)
    )
    return data


def build_feature_frame(raw: dict,
                        follows_threshold: float,
                        followers_threshold: float) -> pd.DataFrame:
    """Build the ordered feature row for one account."""
    df = pd.DataFrame([{k: raw[k] for k in RAW_FEATURES}])
    df = add_row_wise_features(df)
    df = add_threshold_features(df, follows_threshold, followers_threshold)
    return df[FEATURE_COLS]


def username_digit_ratio(username: str) -> float:
    """Digits divided by username length."""
    if not username:
        return 0.0
    digits = sum(ch.isdigit() for ch in username)
    return digits / len(username)


def save_artifacts(model, scaler, thresholds: dict,
                   feature_importance: pd.DataFrame, meta: dict) -> None:
    ARTIFACT_DIR.mkdir(exist_ok=True)
    joblib.dump(model, ARTIFACT_DIR / "model.pkl")
    joblib.dump(scaler, ARTIFACT_DIR / "scaler.pkl")
    with open(ARTIFACT_DIR / "thresholds.json", "w") as f:
        json.dump(thresholds, f, indent=2)
    feature_importance.to_csv(ARTIFACT_DIR / "feature_importance.csv", index=False)
    with open(ARTIFACT_DIR / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)


def load_artifacts():
    """Returns (model, scaler, thresholds)."""
    if not (ARTIFACT_DIR / "model.pkl").exists():
        raise FileNotFoundError(
            "No saved model found. Run:  python train_and_save.py  first."
        )
    model = joblib.load(ARTIFACT_DIR / "model.pkl")
    scaler = joblib.load(ARTIFACT_DIR / "scaler.pkl")
    with open(ARTIFACT_DIR / "thresholds.json") as f:
        thresholds = json.load(f)
    return model, scaler, thresholds


def verdict_label(prob_fake: float, min_confidence: float = 0.60) -> dict:
    """Three-way verdict. Below min_confidence the result is reported as
    uncertain instead of a hard Real/Fake call."""
    confidence = max(prob_fake, 1 - prob_fake)
    if confidence < min_confidence:
        return {"band": "uncertain", "text": "UNCERTAIN - needs review",
                "color": "#d97706", "confidence": confidence, "prob_fake": prob_fake}
    if prob_fake >= 0.5:
        return {"band": "fake", "text": "FAKE / BOT-LIKE",
                "color": "#dc2626", "confidence": confidence, "prob_fake": prob_fake}
    return {"band": "real", "text": "REAL / AUTHENTIC",
            "color": "#16a34a", "confidence": confidence, "prob_fake": prob_fake}


def predict_account(raw: dict, model, scaler, thresholds: dict):
    """Classify one account. Returns (label, prob_fake, features)."""
    feats = build_feature_frame(
        raw,
        thresholds["follows_threshold"],
        thresholds["followers_threshold"],
    )
    X = scaler.transform(feats)
    prob_fake = float(model.predict_proba(X)[0][1])
    label = int(prob_fake >= 0.5)
    return label, prob_fake, feats
