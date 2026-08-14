# ============================================================
# TrustLens — Data Ingestion Module
# Fetches real Instagram profile data using RapidAPI
# ============================================================

import requests
import os
from dotenv import load_dotenv

load_dotenv()  # reads your .env file

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_KEY_COMMENTS = os.getenv("RAPIDAPI_KEY_COMMENTS")
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

    profile_data = {
        "username":          data.get("username", username),
        "followers":         data.get("follower_count", 0),
        "following":         data.get("following_count", 0),
        "posts":             data.get("media_count", 0),
        "has_profile_pic":   bool(data.get("profile_pic_url")),
        "bio_length":        len(data.get("biography", "") or ""),
        "biography":         data.get("biography", "") or "",
        "has_external_url":  bool(data.get("external_url")),
        "is_private":        bool(data.get("is_private", False)),
        "full_name":         data.get("full_name", ""),
        "is_verified":       data.get("is_verified", False)
    }

    return profile_data


def fetch_engagement_data(username: str, amount: int = 12) -> dict:
    """
    Fetches recent posts and calculates real average likes/comments
    for engagement analysis. Also returns post codes for comment analysis.
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

    edges = data.get("posts", [])
    likes = []
    comments = []
    post_codes = []

    for edge in edges:
        node = edge.get("node", edge)
        likes.append(node.get("like_count", 0) or 0)
        comments.append(node.get("comment_count", 0) or 0)
        code = node.get("code")
        if code:
            post_codes.append(code)

    avg_likes = sum(likes) / len(likes) if likes else 0
    avg_comments = sum(comments) / len(comments) if comments else 0

    return {
        "avg_likes": round(avg_likes, 1),
        "avg_comments": round(avg_comments, 1),
        "posts_analyzed": len(likes),
        "post_codes": post_codes
    }


def fetch_post_comments(media_code: str, sort_order: str = "popular") -> list:
    """
    Fetches comments for a single post, returns list of comment text strings.
    """
    COMMENTS_URL = f"https://{RAPIDAPI_HOST}/get_post_comments.php"

    headers = {
        "content-type": "application/json",
        "x-rapidapi-host": RAPIDAPI_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY_COMMENTS
    }

    params = {
        "media_code": media_code,
        "sort_order": sort_order
    }

    response = requests.get(COMMENTS_URL, headers=headers, params=params)

    if response.status_code != 200:
        return []

    data = response.json()
    comments = data.get("comments", [])

    texts = []
    for c in comments:
        text = c.get("text", "")
        if text:
            texts.append(text.strip())

    return texts