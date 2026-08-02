# ============================================================
# TrustLens — Fake Follower Detection Module
# ============================================================

import pickle
import numpy as np
import os

# Load the trained model from our paper implementation
MODEL_PATH = "fake_follower_model.pkl"

def analyze_fake_followers(followers, following, posts,
                           has_profile_pic, bio_length,
                           has_external_url, is_private):

    # ---- Feature Engineering (same as paper implementation) ----
    follower_follow_ratio = followers / (following + 1)
    posts_per_follower    = posts / (followers + 1)
    has_bio               = 1 if bio_length > 0 else 0
    engagement_score_raw  = (posts * 0.4 + followers * 0.4 + following * 0.2) / 1000
    suspicious_username   = 0  # default — no username passed here

    features = np.array([[
        has_profile_pic,
        0.0,                    # nums/length username — default
        1,                      # fullname words — default
        0.0,                    # nums/length fullname — default
        0,                      # name==username — default
        bio_length,
        has_external_url,
        is_private,
        posts,
        followers,
        following,
        follower_follow_ratio,
        posts_per_follower,
        has_bio,
        engagement_score_raw,
        suspicious_username
    ]])

    # ---- If model exists load it, otherwise use rule-based ----
    if os.path.exists(MODEL_PATH):
        with open(MODEL_PATH, "rb") as f:
            model = pickle.load(f)
        prediction    = model.predict(features)[0]
        probability   = model.predict_proba(features)[0]
        bot_prob      = float(probability[1])
    else:
        # Rule-based fallback when model file not present
        bot_prob = rule_based_detection(
            followers, following, posts,
            has_profile_pic, bio_length,
            follower_follow_ratio
        )
        prediction = 1 if bot_prob > 0.5 else 0

    bot_percentage = round(bot_prob * 100, 1)

    # ---- Verdict ----
    if bot_percentage >= 70:
        verdict = "High Risk — Likely Fake"
        color   = "red"
    elif bot_percentage >= 40:
        verdict = "Moderate Risk — Suspicious"
        color   = "yellow"
    else:
        verdict = "Low Risk — Likely Genuine"
        color   = "green"

    return {
        "bot_percentage":        bot_percentage,
        "verdict":               verdict,
        "color":                 color,
        "follower_follow_ratio": round(follower_follow_ratio, 2),
        "posts_per_follower":    round(posts_per_follower, 4),
        "has_bio":               bool(has_bio),
        "prediction":            int(prediction)
    }


def rule_based_detection(followers, following, posts,
                          has_profile_pic, bio_length,
                          follower_follow_ratio):
    score = 0.0

    if not has_profile_pic:
        score += 0.30
    if bio_length == 0:
        score += 0.20
    if follower_follow_ratio < 0.1:
        score += 0.25
    if posts == 0:
        score += 0.15
    if following > 2000 and followers < 100:
        score += 0.10

    return min(score, 1.0)