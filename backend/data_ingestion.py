# ============================================================
# TrustLens — Data Ingestion Module
# Fetches real Instagram profile data using RapidAPI
# ============================================================

import re
import requests
import os
from dotenv import load_dotenv

# Load backend/.env by its own location, so the keys are found no matter
# which folder the program was started from.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_KEY_COMMENTS = os.getenv("RAPIDAPI_KEY_COMMENTS")
RAPIDAPI_HOST = "instagram-scraper-stable-api.p.rapidapi.com"
RAPIDAPI_URL = f"https://{RAPIDAPI_HOST}/ig_get_fb_profile_v3.php"


class ProfileNotFoundError(Exception):
    """The username itself is the problem (typo'd, deleted, never existed) —
    not a network hiccup. Kept as its own type, not just a string, so the
    frontend can show "check the spelling" instead of "try again" without
    fragile matching on the exact wording of a message."""
    pass


def _post_with_retry(url, headers, payload, timeout, label):
    """One retry on a timeout/connection error before giving up.

    This network stalls occasionally (documented repeatedly in this project)
    and a lone retry clears most of those — RapidAPI's own dashboard confirms
    a failed request due to a stall isn't billed, so a retry costs nothing.
    A real "this account doesn't exist" response comes back fast and clean,
    so it is never retried here — only network-level failures are.
    """
    last_exc = None
    for attempt in range(2):
        try:
            return requests.post(url, headers=headers, data=payload, timeout=timeout)
        except requests.exceptions.Timeout as e:
            last_exc = e
        except requests.exceptions.RequestException as e:
            raise Exception(f"Could not reach {label}: {e}")
    raise TimeoutError(
        f"{label} took too long to respond, twice in a row (over {timeout}s each time). "
        f"This is a temporary network issue, not a problem with the username — please try again shortly."
    )


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

    response = _post_with_retry(RAPIDAPI_URL, headers, payload, 20, "Instagram")

    if response.status_code != 200:
        raise Exception(f"Instagram API failed with status {response.status_code}")

    data = response.json()

    # A missing account comes back as HTTP 200 with {"error": "...does not
    # exist..."}. Reading that with .get(..., 0) used to turn it into a profile
    # with 0 followers, 0 posts and no picture, which the fake-account model
    # then scored as a certain bot. Refuse it instead of inventing data.
    if not isinstance(data, dict) or data.get("error") or "follower_count" not in data:
        reason = data.get("error") if isinstance(data, dict) else None
        # RapidAPI's own wording for a bad username always mentions "invalid"
        # or "exist". Anything else in that field (quota, a malformed request)
        # is a real backend problem, not a bad username — don't tell the user
        # their spelling is wrong when it might not be.
        if reason is None or re.search(r"invalid|exist", reason, re.I):
            raise ProfileNotFoundError(
                f"There's no public Instagram account called '{username}'. Check the spelling — "
                f"private accounts and typos both come back this way."
            )
        raise Exception(f"Instagram API error: {reason}")

    profile_data = {
        "username":          data.get("username", username),
        "followers":         data.get("follower_count", 0),
        "following":         data.get("following_count", 0),
        "posts":             data.get("media_count", 0),
        "has_profile_pic":   bool(data.get("profile_pic_url")),
        "profile_pic_url":   data.get("profile_pic_url", "") or "",
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

    response = _post_with_retry(POSTS_URL, headers, payload, 20, "Instagram posts API")

    if response.status_code != 200:
        raise Exception(f"Posts fetch failed with status {response.status_code}")

    data = response.json()

    edges = data.get("posts", [])
    likes = []
    comments = []
    post_codes = []
    post_captions = []
    # One entry per post, for the engagement trend chart (Visual Analytics).
    # Same numbers the averages below are built from, just not averaged.
    posts = []

    for edge in edges:
        node = edge.get("node", edge)
        like_n = node.get("like_count", 0) or 0
        comment_n = node.get("comment_count", 0) or 0
        likes.append(like_n)
        comments.append(comment_n)
        code = node.get("code")
        if code:
            post_codes.append(code)
        taken_at = node.get("taken_at") or node.get("taken_at_timestamp")
        posts.append({
            "code": code,
            "likes": like_n,
            "comments": comment_n,
            "comments_off": bool(node.get("comments_disabled") or node.get("commenting_disabled_for_viewer")),
            "taken_at": int(taken_at) if isinstance(taken_at, (int, float)) else None,
            "is_video": bool(node.get("is_video") or node.get("media_type") == 2),
        })

        caption_obj = node.get("caption")
        caption_text = (caption_obj or {}).get("text", "") if caption_obj else ""
        if caption_text and caption_text.strip():
            post_captions.append(caption_text.strip())

    avg_likes = sum(likes) / len(likes) if likes else 0
    avg_comments = sum(comments) / len(comments) if comments else 0

    # Comments turned off or restricted by the creator. Instagram then reports
    # comment_count 0 on every post, which is a setting, not "nobody comments".
    # Only concluded when EVERY post shows 0 comments AND most of them carry
    # Instagram's own comments-disabled marker; otherwise zero is a real zero.
    off = sum(1 for p in posts if p["comments_off"])
    comments_off = bool(posts) and not any(comments) and off >= len(posts) / 2

    return {
        "avg_likes": round(avg_likes, 1),
        "avg_comments": round(avg_comments, 1),
        "posts_analyzed": len(likes),
        "post_codes": post_codes,
        "post_captions": post_captions,
        "posts": posts,
        "comments_off": comments_off,
    }


def fetch_media_data(media_code: str) -> dict:
    """
    Fetches one post or reel by its shortcode (the ABC123 in /reel/ABC123/).
    Used by the browser extension: the real caption, the real poster and the
    direct video file come from here instead of being guessed from the page.
    """
    MEDIA_URL = f"https://{RAPIDAPI_HOST}/get_media_data_v2.php"

    headers = {
        "x-rapidapi-host": RAPIDAPI_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY
    }

    try:
        response = requests.get(MEDIA_URL, headers=headers,
                                params={"media_code": media_code}, timeout=20)
    except requests.exceptions.Timeout:
        raise Exception("Instagram media API took too long to respond (over 20s).")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Could not reach Instagram media API: {e}")

    if response.status_code != 200:
        raise Exception(f"Media fetch failed with status {response.status_code}")

    data = response.json()
    if not isinstance(data, dict) or not data.get("code"):
        raise Exception("Instagram returned no data for this post (deleted, private, or not found).")

    user = data.get("user") or {}
    caption_obj = data.get("caption") or {}
    videos = data.get("video_versions") or []
    # Carousels keep their video inside the first video slide.
    if not videos:
        for slide in data.get("carousel_media") or []:
            if slide.get("video_versions"):
                videos = slide["video_versions"]
                break

    return {
        "code":          data.get("code"),
        "caption":       (caption_obj.get("text") or "").strip(),
        "username":      user.get("username", "") or "",
        "full_name":     user.get("full_name", "") or "",
        "is_verified":   bool(user.get("is_verified", False)),
        "is_private":    bool(user.get("is_private", False)),
        "is_video":      bool(videos),
        "has_audio":     bool(data.get("has_audio", bool(videos))),
        "video_url":     videos[0].get("url", "") if videos else "",
        "like_count":    data.get("like_count") or 0,
        "comment_count": data.get("comment_count") or 0,
        "taken_at":      data.get("taken_at"),
        "product_type":  data.get("product_type", ""),
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

    try:
        response = requests.get(COMMENTS_URL, headers=headers, params=params, timeout=15)
    except requests.exceptions.RequestException:
        return []

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