"""
instagram_fetch.py
-------------------
Extends the Data Ingestion Pipeline pattern (same RapidAPI endpoint
your teammate uses) to actually pull caption TEXT — his current
fetch_engagement_data() only pulls like/comment counts, not the
caption itself, which is what the Misinformation Classifier needs.

This is an interim/testing tool so you can validate your model against
real posts right now. Once you sync with your teammate, the real
caption extraction should live in his data_ingestion.py so there's one
source of truth — flag this file to him.

IMPORTANT: I can't verify the exact JSON field name for captions
without a live API key/response. This tries several common field
names used by Instagram-scraper APIs (caption.text, caption, text,
description) and falls back gracefully. If none match, run with
DEBUG=1 to print the raw response and find the correct field, then
adjust CAPTION_FIELD_CANDIDATES below.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = "instagram-scraper-stable-api.p.rapidapi.com"
POSTS_URL = f"https://{RAPIDAPI_HOST}/get_ig_user_posts.php"

# Confirmed working (2026-08-08) via RapidAPI's Code Snippets tab:
#   GET https://.../get_media_data.php?reel_post_code_or_url=<full URL, encoded>&type=post|reel
POST_INFO_URL = f"https://{RAPIDAPI_HOST}/get_media_data.php"

DEBUG = os.getenv("DEBUG", "0") == "1"


def _extract_caption(node: dict) -> str:
    """Tries several likely field shapes for the caption text."""
    caption = node.get("caption")
    if isinstance(caption, dict):
        text = caption.get("text")
        if text:
            return text
    if isinstance(caption, str) and caption:
        return caption
    for key in ("text", "description", "edge_media_to_caption"):
        val = node.get(key)
        if isinstance(val, str) and val:
            return val
        if isinstance(val, dict):
            edges = val.get("edges")
            if edges:
                try:
                    return edges[0]["node"]["text"]
                except (KeyError, IndexError, TypeError):
                    pass
    return ""


def _extract_like_count(node: dict) -> int:
    """Confirmed real shape (from Detailed Post Data): edge_media_preview_like.count"""
    if "like_count" in node:
        return node.get("like_count", 0) or 0
    likes = node.get("edge_media_preview_like") or node.get("edge_liked_by")
    if isinstance(likes, dict):
        return likes.get("count", 0) or 0
    return 0


def _extract_comment_count(node: dict) -> int:
    """Confirmed real shape (from Detailed Post Data): edge_media_to_comment.count"""
    if "comment_count" in node:
        return node.get("comment_count", 0) or 0
    comments = node.get("edge_media_to_comment")
    if isinstance(comments, dict):
        return comments.get("count", 0) or 0
    return 0


def fetch_recent_captions(username: str, amount: int = 12) -> list[dict]:
    """
    Fetches recent posts for a username and returns a list of
    {post_id, caption, like_count, comment_count} dicts — ready to
    feed straight into classify_text().
    """
    if not RAPIDAPI_KEY:
        raise RuntimeError("RAPIDAPI_KEY not set in .env")

    headers = {
        "content-type": "application/x-www-form-urlencoded",
        "x-rapidapi-host": RAPIDAPI_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY,
    }
    payload = {"username_or_url": username, "pagination_token": "", "amount": amount}

    response = requests.post(POSTS_URL, headers=headers, data=payload)
    if response.status_code != 200:
        raise Exception(f"Posts fetch failed with status {response.status_code}")

    data = response.json()
    if DEBUG:
        print("RAW API RESPONSE:", data)

    edges = data.get("posts", [])
    results = []
    for edge in edges:
        node = edge.get("node", edge)
        caption = _extract_caption(node)
        results.append({
            "post_id": node.get("id") or node.get("shortcode") or "",
            "caption": caption,
            "like_count": _extract_like_count(node),
            "comment_count": _extract_comment_count(node),
        })
    return results


def fetch_latest_post(username: str) -> dict:
    """Convenience wrapper: just the single most recent post for a
    username, for when you only need to prove the pipeline works on
    one real post rather than fetching a whole batch."""
    posts = fetch_recent_captions(username, amount=1)
    if not posts:
        raise Exception(f"No posts found for '{username}' (private account or no public posts)")
    return posts[0]


def fetch_post_by_shortcode(post_url: str, media_type: str = "post") -> dict:
    """
    Fetches a single post/reel by its full URL (confirmed endpoint,
    tested against a real 7-slide carousel post on 2026-08-08).

    post_url: the FULL original Instagram URL (this endpoint needs the
              whole URL, not just the shortcode).
    media_type: "post" or "reel" — passed straight to the API's `type` param.
    """
    if not RAPIDAPI_KEY:
        raise RuntimeError("RAPIDAPI_KEY not set in .env")

    headers = {
        "x-rapidapi-host": RAPIDAPI_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY,
    }
    params = {"reel_post_code_or_url": post_url, "type": media_type}

    response = requests.get(POST_INFO_URL, headers=headers, params=params)
    if response.status_code != 200:
        raise Exception(f"Post fetch failed with status {response.status_code}: {response.text[:200]}")

    data = response.json()
    if DEBUG:
        print("RAW API RESPONSE:", data)

    # The confirmed response returns the post's fields directly (not
    # wrapped in a "post" key), matching a carousel post structure.
    node = data.get("post", data)
    caption = _extract_caption(node)
    return {
        "post_id": node.get("id") or node.get("shortcode") or "",
        "caption": caption,
        "like_count": _extract_like_count(node),
        "comment_count": _extract_comment_count(node),
    }