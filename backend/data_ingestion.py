# ============================================================
# TrustLens — Data Ingestion Module
# Fetches real Instagram profile data using RapidAPI
# ============================================================

import requests
import os
from dotenv import load_dotenv

load_dotenv()  # reads your .env file

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = "instagram-scraper-stable-api.p.rapidapi.com"
RAPIDAPI_URL = f"https://{RAPIDAPI_HOST}/ig_get_fb_profile_v3.php"


def fetch_instagram_profile(username: str) -> dict:
    """
    Calls RapidAPI's Instagram Scraper to get real profile data,
    then converts it into the exact fields our AI model needs.
    """

    headers = {
        "content-type": "application/x-www-form-urlencoded",
        "x-rapidapi-host": RAPIDAPI_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY
    }

    payload = {
        "username_or_url": username
    }

    response = requests.post(RAPIDAPI_URL, headers=headers, data=payload)

    if response.status_code != 200:
        raise Exception(f"Instagram API failed with status {response.status_code}")

    data = response.json()

    # ---- Convert raw API response into our model's expected fields ----
    profile_data = {
        "username":          data.get("username", username),
        "followers":         data.get("follower_count", 0),
        "following":         data.get("following_count", 0),
        "posts":             data.get("media_count", 0),
        "has_profile_pic":   bool(data.get("profile_pic_url")),
        "bio_length":        len(data.get("biography", "") or ""),
        "has_external_url":  bool(data.get("external_url")),
        "is_private":        bool(data.get("is_private", False)),
        "full_name":         data.get("full_name", ""),
        "is_verified":       data.get("is_verified", False)
    }

    return profile_data

def fetch_engagement_data(username: str, amount: int = 12) -> dict:
    """
    Fetches recent posts and calculates real average likes/comments
    for engagement analysis.
    """
    POSTS_URL = f"https://{RAPIDAPI_HOST}/get_ig_user_posts.php"

    headers = {
        "content-type": "application/x-www-form-urlencoded",
        "x-rapidapi-host": RAPIDAPI_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY
    }

    payload = {
        "username_or_url": username,
        "pagination_token": "",
        "amount": amount
    }

    response = requests.post(POSTS_URL, headers=headers, data=payload)

    if response.status_code != 200:
        raise Exception(f"Posts fetch failed with status {response.status_code}")

    data = response.json()

    # ---- Extract likes/comments from each post ----
    edges = data.get("posts", [])
    likes = []
    comments = []

    for edge in edges:
        node = edge.get("node", edge)
        likes.append(node.get("like_count", 0) or 0)
        comments.append(node.get("comment_count", 0) or 0)

    avg_likes = sum(likes) / len(likes) if likes else 0
    avg_comments = sum(comments) / len(comments) if comments else 0

    return {
        "avg_likes": round(avg_likes, 1),
        "avg_comments": round(avg_comments, 1),
        "posts_analyzed": len(likes)
    }