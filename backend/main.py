# ============================================================
# TrustLens — Main FastAPI Backend
# ============================================================

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fake_follower import analyze_fake_followers
from engagement_analyzer import analyze_engagement
from trust_score import calculate_trust_score
from data_ingestion import fetch_instagram_profile

app = FastAPI(
    title="TrustLens API",
    description="AI-Powered Influencer Authenticity Detection",
    version="1.0.0"
)

# Allow React frontend to talk to this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {
        "message": "TrustLens API is running",
        "version": "1.0.0",
        "status": "active"
    }

@app.post("/analyze")
def analyze_profile(data: dict):
    username        = data.get("username", "unknown")
    followers       = data.get("followers", 0)
    following       = data.get("following", 0)
    posts           = data.get("posts", 0)
    likes_avg       = data.get("likes_avg", 0)
    comments_avg    = data.get("comments_avg", 0)
    has_profile_pic = data.get("has_profile_pic", 1)
    bio_length      = data.get("bio_length", 0)
    has_external_url= data.get("has_external_url", 0)
    is_private      = data.get("is_private", 0)

    # Run all modules
    fake_result       = analyze_fake_followers(
        followers, following, posts,
        has_profile_pic, bio_length, has_external_url, is_private
    )

    engagement_result = analyze_engagement(
        followers, likes_avg, comments_avg, posts
    )

    trust_result = calculate_trust_score(
        fake_result["bot_percentage"],
        engagement_result["engagement_score"]
    )

    return {
        "username": username,
        "fake_follower_analysis": fake_result,
        "engagement_analysis": engagement_result,
        "trust_score": trust_result
    }

@app.post("/analyze-live")
def analyze_profile_live(data: dict):
    username = data.get("username")

    if not username:
        return {"error": "Please provide a username"}

    # ---- Fetch real Instagram data ----
    try:
        profile = fetch_instagram_profile(username)
    except Exception as e:
        return {"error": f"Could not fetch Instagram data: {str(e)}"}

    # ---- Run Fake Follower Detection ----
    fake_result = analyze_fake_followers(
        profile["followers"], profile["following"], profile["posts"],
        profile["has_profile_pic"], profile["bio_length"],
        profile["has_external_url"], profile["is_private"]
    )

    # ---- Run Engagement Analyzer ----
    # Note: real like/comment averages aren't available from this API yet,
    # so we pass 0 for now — this is a known gap to flag to your supervisor
    engagement_result = analyze_engagement(
        profile["followers"], 0, 0, profile["posts"]
    )

    # ---- Combine into Trust Score ----
    trust_result = calculate_trust_score(
        fake_result["bot_percentage"],
        engagement_result["engagement_score"]
    )

    return {
        "username": profile["username"],
        "full_name": profile["full_name"],
        "is_verified": profile["is_verified"],
        "raw_profile_data": profile,
        "fake_follower_analysis": fake_result,
        "engagement_analysis": engagement_result,
        "trust_score": trust_result
    }