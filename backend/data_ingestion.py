# ============================================================
# TrustLens — Data Ingestion Module
# Fetches real Instagram profile data using RapidAPI
# ============================================================

import re
import time
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
            response = requests.post(url, headers=headers, data=payload, timeout=timeout)
        except requests.exceptions.Timeout as e:
            last_exc = e
            continue
        except requests.exceptions.ConnectionError as e:
            # e.g. "connection reset by peer" - the same kind of stall as a timeout
            last_exc = e
            continue
        except requests.exceptions.RequestException as e:
            raise Exception(f"Could not reach {label}: {e}")
        # The provider occasionally answers 200 with a JSON list instead of the
        # usual object (seen on real accounts, gone on the next try). Treat that
        # as a hiccup and ask once more instead of crashing on it later.
        if response.status_code == 200:
            try:
                if not isinstance(response.json(), dict):
                    last_exc = ValueError("unexpected reply shape")
                    continue
            except ValueError:
                last_exc = ValueError("reply was not JSON")
                continue
        return response
    if isinstance(last_exc, ValueError):
        raise Exception(f"{label} sent an unexpected reply twice in a row. "
                        f"This is a temporary problem on their side - please try again shortly.")
    raise TimeoutError(
        f"{label} took too long to respond, twice in a row (over {timeout}s each time). "
        f"This is a temporary network issue, not a problem with the username — please try again shortly."
    )


# The provider sometimes answers that IT is being rate-limited by Instagram,
# e.g. {"error": "Profile data not found. Received 429 Too Many Requests."}.
# Seen on 2026-10-22 for @leomessi and @shakira; the same requests succeeded a
# few seconds later. So those replies are retried after a short wait instead of
# failing the scan. (A real "this account doesn't exist" reply is never retried.)
_BUSY = re.compile(r"429|too many requests|rate.?limit|try again later", re.I)
BUSY_WAITS = (2.0, 4.0)


def _provider_busy(data) -> bool:
    return isinstance(data, dict) and bool(_BUSY.search(str(data.get("error") or "")))


def _post_json_patiently(url, headers, payload, timeout, label):
    """_post_with_retry, plus up to two waits when the provider says it is busy.
    Returns (response, data)."""
    for wait in (*BUSY_WAITS, None):
        response = _post_with_retry(url, headers, payload, timeout, label)
        data = response.json() if response.status_code == 200 else None
        if wait is None or not _provider_busy(data):
            return response, data
        time.sleep(wait)


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

    response, data = _post_json_patiently(RAPIDAPI_URL, headers, payload, 20, "Instagram")

    if response.status_code != 200:
        raise Exception(f"Instagram API failed with status {response.status_code}")

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
        if _provider_busy(data):
            raise Exception("Instagram is limiting requests right now (it said \"too many requests\"), "
                            "even after waiting and trying again. Please try again in a minute.")
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


def audio_url_from_manifest(mpd) -> str:
    """Instagram streams a reel as separate video and audio tracks, described
    in `video_dash_manifest` (an MPEG-DASH XML document). Returns the link to
    the lowest-bitrate audio-only track (plenty for speech: ~0.5 MB a minute
    against 7-19 MB for the video), or "" if there isn't one. Same rule the
    browser extension uses (extension/page_hook.js, audioOf)."""
    if not isinstance(mpd, str) or "audio" not in mpd:
        return ""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(mpd)
    except ET.ParseError:
        return ""

    def local(tag):
        return tag.rsplit("}", 1)[-1]

    best_url, best_bw = "", None
    for aset in root.iter():
        if local(aset.tag) != "AdaptationSet":
            continue
        set_kind = (aset.get("mimeType") or "") + " " + (aset.get("contentType") or "")
        for rep in aset:
            if local(rep.tag) != "Representation":
                continue
            if "audio" not in (rep.get("mimeType") or "") + " " + set_kind:
                continue
            base = next((c for c in rep.iter() if local(c.tag) == "BaseURL"), None)
            if base is None or not (base.text or "").strip():
                continue
            try:
                bw = float(rep.get("bandwidth") or "inf")
            except ValueError:
                bw = float("inf")
            if best_bw is None or bw < best_bw:
                best_url, best_bw = base.text.strip(), bw
    return best_url


def reel_media(node: dict) -> dict | None:
    """The sound sources of one post, if it is a video: its audio-only track
    and its video file. None for photos. Used by the Video-to-Text module."""
    videos = node.get("video_versions") or []
    if not videos and not node.get("video_dash_manifest"):
        return None
    has_audio = node.get("has_audio")
    taken_at = node.get("taken_at") or node.get("taken_at_timestamp")
    return {
        "code": node.get("code"),
        "audio_url": audio_url_from_manifest(node.get("video_dash_manifest")),
        "video_url": (videos[0].get("url") or "") if videos else "",
        "has_audio": has_audio is not False,
        "taken_at": int(taken_at) if isinstance(taken_at, (int, float)) else None,
        "product_type": node.get("product_type") or "",
    }


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

    response, data = _post_json_patiently(POSTS_URL, headers, payload, 20, "Instagram posts API")

    if response.status_code != 200:
        raise Exception(f"Posts fetch failed with status {response.status_code}")

    # An error reply used to be read as "this account has no posts", which
    # quietly turned engagement into "not measured". Say what happened instead.
    if isinstance(data, dict) and data.get("error") and "posts" not in data:
        if _provider_busy(data):
            raise Exception("Instagram is limiting requests right now (it said \"too many requests\"), "
                            "even after waiting and trying again. Please try again in a minute.")
        raise Exception(f"Instagram posts API error: {data.get('error')}")

    edges = data.get("posts", [])
    likes = []
    comments = []
    post_codes = []
    post_captions = []
    # One entry per post, for the engagement trend chart (Visual Analytics).
    # Same numbers the averages below are built from, just not averaged.
    posts = []
    # Sound sources of the video posts, for the Video-to-Text module. These
    # are signed links that expire within hours, so scan_service uses them
    # during the scan and does not store them.
    reels = []

    for edge in edges:
        node = edge.get("node", edge)
        media = reel_media(node)
        if media and media["code"] and (media["audio_url"] or media["video_url"]):
            reels.append(media)
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
        "reel_media": reels,
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

    data = None
    for attempt in range(2):
        try:
            response = requests.get(MEDIA_URL, headers=headers,
                                    params={"media_code": media_code}, timeout=20)
        except requests.exceptions.Timeout:
            if attempt:
                raise Exception("Instagram media API took too long to respond (over 20s).")
            continue
        except requests.exceptions.RequestException as e:
            raise Exception(f"Could not reach Instagram media API: {e}")
        if response.status_code != 200:
            raise Exception(f"Media fetch failed with status {response.status_code}")
        try:
            data = response.json()
        except ValueError:
            data = None
        if isinstance(data, dict) and data.get("code"):
            break
        # Seen on 2026-10-21: the provider answered {"error": "Media data not
        # found. Try again later."} for every post for a while. One retry,
        # then report what the provider actually said.
        if attempt == 0:
            time.sleep(1.5)
    if not isinstance(data, dict) or not data.get("code"):
        said = data.get("error") if isinstance(data, dict) else None
        raise Exception(f"Instagram's data service didn't return this post"
                        + (f' ("{said}")' if said else "") + ".")

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
        "audio_url":     audio_url_from_manifest(data.get("video_dash_manifest")),
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