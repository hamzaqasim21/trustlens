# ============================================================
# TrustLens — the scan pipeline, in one place
# ============================================================
#
# Every way of scanning an account runs THIS function, so they can never
# disagree with each other:
#   - the Scan page and the Comparison page      (source "web")
#   - an automatic re-check of a watched account  (source "watchlist")
#   - a brand's bulk analysis / API key           (source "bulk" / "api")
#   - a creator re-scanning their own account     (source "creator")
#
# It used to live inside main.py's /analyze-live handler; it was moved here
# unchanged when those other entry points were added, so each of them is a
# thin wrapper around the same real pipeline, not a copy of it.

import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "misinfo_classifier", "api"))
from model_loader import classify_text  # noqa: E402

from fake_follower import analyze_fake_followers, name_features  # noqa: E402
from misinfo_assessment import assess_text, worst  # noqa: E402
from engagement_analyzer import analyze_engagement, analyze_comment_authenticity  # noqa: E402
from trust_score import calculate_trust_score  # noqa: E402
from data_ingestion import (  # noqa: E402
    fetch_instagram_profile, fetch_engagement_data, fetch_post_comments, fetch_media_data,
    ProfileNotFoundError,
)
import video_transcriber  # noqa: E402
from credential_extractor import calculate_credential_confidence  # noqa: E402
from database import ScanHistory  # noqa: E402

SOURCES = {"web", "watchlist", "bulk", "api", "creator"}

# Module 12 (Video-to-Text): how many of the account's most recent reels are
# listened to in each scan, and the most time the scan waits for them. It is a
# hard limit: found in a browser test (2026-10-21) that a reel whose downloads
# kept failing, plus a second scan queued behind it, held a scan for over five
# minutes when the limit was only checked between reels. A reel not finished
# in time is reported as "not listened to", never as clean; its transcription
# carries on in the background and is reused by the next scan.
REELS_PER_SCAN = 3
REEL_TIME_BUDGET = 45.0
TIME_LIMIT_NOTE = "not listened to: this scan's time limit for reels was reached"

# Reel speech only counts in languages the misinformation model was trained
# and tested on. Whisper transcribes ~99 languages, so others are still shown,
# but there is no accuracy evidence for judging them, so they aren't scored.
SCORED_LANGUAGES = {"en", "ur"}


class ScanFailed(Exception):
    """A scan that could not produce a result. `kind` lets every caller tell
    "that account doesn't exist" (not_found) from "Instagram was slow" (network)."""

    def __init__(self, message, kind="network"):
        super().__init__(message)
        self.kind = kind


# --------------------------------------------------------------------------- #
# What the user typed: a username, a profile link, or a post/reel link
# --------------------------------------------------------------------------- #
_POST_LINK = re.compile(r"instagram\.com/(?:[A-Za-z0-9._]+/)?(?:reels?|p|tv)/([A-Za-z0-9_-]{5,40})", re.I)
_PROFILE_LINK = re.compile(r"instagram\.com/(?:stories/)?([A-Za-z0-9._]{1,30})/", re.I)
_NOT_PROFILES = {"explore", "accounts", "direct", "stories", "reels", "reel", "p", "tv",
                 "about", "developer", "legal"}


def username_in_post_link(text):
    """The account name in a link like instagram.com/<user>/reel/<code>, if any."""
    m = re.search(r"instagram\.com/([A-Za-z0-9._]{1,30})/(?:reels?|p|tv)/", text or "", re.I)
    return m.group(1) if m and m.group(1).lower() not in _NOT_PROFILES else None


def parse_scan_input(text):
    """Returns ("post", shortcode) for a post/reel link, ("username", name)
    for a profile link or a plain username, or (None, None) if empty."""
    text = (text or "").strip()
    if not text:
        return None, None
    if "instagram.com" in text.lower():
        m = _POST_LINK.search(text)
        if m:
            return "post", m.group(1)
        m = _PROFILE_LINK.search(text.split("?")[0].split("#")[0].rstrip("/") + "/")
        if m and m.group(1).lower() not in _NOT_PROFILES:
            return "username", m.group(1)
        raise ScanFailed("That Instagram link isn't a profile, post or reel link.", "invalid")
    return "username", text.lstrip("@").strip()


# --------------------------------------------------------------------------- #
# Module 12: listen to the account's reels
# --------------------------------------------------------------------------- #
def _pick_reels(reel_media, focus=None):
    """The submitted reel first (if any), then the newest reels that have
    sound, up to REELS_PER_SCAN in total."""
    picked, seen = [], set()
    if focus and focus.get("code"):
        picked.append(dict(focus, submitted=True))
        seen.add(focus["code"])
    newest = sorted((r for r in reel_media if r.get("has_audio")),
                    key=lambda r: r.get("taken_at") or 0, reverse=True)
    for r in newest:
        if len(picked) >= REELS_PER_SCAN:
            break
        if r["code"] not in seen:
            picked.append(dict(r, submitted=False))
            seen.add(r["code"])
    return picked


def _reel_base(r):
    return {"code": r["code"], "url": f"https://www.instagram.com/reel/{r['code']}/",
            "submitted": bool(r.get("submitted"))}


def _listen_to_reels(reels, transcribe=None, heard=None):
    """Transcribe each reel, appending to `heard` as each one finishes (so a
    scan that stops waiting can still use the ones already done). Never raises."""
    transcribe = transcribe or video_transcriber.transcribe_reel
    started = time.monotonic()
    heard = [] if heard is None else heard
    for r in reels:
        base = _reel_base(r)
        if time.monotonic() - started > REEL_TIME_BUDGET:
            heard.append(dict(base, available=False, error=TIME_LIMIT_NOTE))
            continue
        try:
            t = transcribe(r["code"], r.get("audio_url") or "", r.get("video_url") or "",
                           careful=bool(r.get("submitted")))
        except Exception as e:  # transcribe_reel shouldn't raise; be safe anyway
            t = {"available": False, "error": f"couldn't listen to this reel ({e})"}
        heard.append(dict(base, **t))
    return heard


def _unbacked_urdu_label(heard, assessment):
    """Urdu speech labelled as misinformation with no hard red flag behind it.

    Measured 2026-10-21 on four ordinary reels by Pakistani creators (Ducky
    Bhai, Irfan Junejo): the classifier called two of them "Urdu
    misinformation" at 99% confidence, with both Whisper models. That class
    was trained on Urdu news articles (UrduFake) and its held-out precision
    was already the lowest of all (0.44). So, as with the "financial scam"
    label (misinfo_assessment.py), the label only counts when a rule backs it.
    """
    is_urdu = heard.get("language") == "ur"
    return (is_urdu and assessment.get("misinformation_flag")
            and not assessment.get("red_flags"))


def _transcription_section(reel_media, heard, focus=None):
    """The Video-to-Text part of the result, ready for the Results page."""
    with_sound = sum(1 for r in reel_media if r.get("has_audio"))
    listened = [h for h in heard if h.get("available")]
    counted = [h for h in listened if h.get("counted")]
    if not heard:
        if focus and focus.get("is_video") is None:
            message = ("The submitted post isn't among this account's 12 most recent posts, and "
                       "Instagram's data service couldn't open it directly, so it wasn't listened to.")
        elif focus and not focus.get("is_video"):
            message = "The submitted link is a photo post, so there was no speech to listen to."
        elif reel_media and not with_sound:
            message = "This account's recent videos have no sound to listen to."
        else:
            message = "No reels among this account's recent posts, so there was no speech to listen to."
        status = "no_reels"
    elif not listened:
        status, message = "unavailable", "The reels couldn't be listened to this time (see each reel for why)."
    else:
        status = "done"
        message = (f"Listened to {len(listened)} reel{'s' if len(listened) != 1 else ''}; "
                   f"the speech in {len(counted)} counted toward the score. "
                   f"Each reel below says why it did or didn't.")
    return {
        "status": status,
        "message": message,
        "reels_in_recent_posts": len(reel_media),
        "reels_with_sound": with_sound,
        "reels_listened": len(listened),
        "reels_counted": len(counted),
        "seconds_per_reel": video_transcriber.MAX_AUDIO_SECONDS,
        "items": heard,
    }


def analyze_username(username: str, focus=None, transcribe=None) -> dict:
    """Fetch the account and run all the modules. No database access.

    `focus` is a submitted post/reel (from fetch_media_data): it is always
    listened to and its caption always checked, even if it is older than the
    12 most recent posts. `transcribe` replaces the speech model in tests."""
    # Profile and engagement data don't depend on each other, so both
    # RapidAPI calls run at the same time instead of one after the other.
    with ThreadPoolExecutor(max_workers=2) as pool:
        profile_future = pool.submit(fetch_instagram_profile, username)
        engagement_future = pool.submit(fetch_engagement_data, username)
        try:
            profile = profile_future.result()
        except ProfileNotFoundError as e:
            raise ScanFailed(str(e), "not_found")
        except Exception as e:
            raise ScanFailed(f"Could not fetch Instagram data: {e}", "network")
        try:
            engagement_data = engagement_future.result()
        except Exception as e:
            raise ScanFailed(f"Could not fetch engagement data: {e}", "network")

    # Module 12 starts listening now, while the other checks run. The reel
    # links expire within hours, so they are taken out of what gets stored.
    reel_media = engagement_data.pop("reel_media", None) or []
    if focus and focus.get("code_only"):
        # The post's own data couldn't be fetched; use it if it is one of the
        # account's recent reels, otherwise say so on the Results page.
        match = next((r for r in reel_media if r["code"] == focus["code"]), None)
        focus = dict(match, is_video=True, caption="") if match else dict(focus, is_video=None)
    reels = _pick_reels(reel_media, focus if (focus and focus.get("is_video")) else None)
    listen_pool = ThreadPoolExecutor(max_workers=1)
    heard_so_far = []
    listen_started = time.monotonic()
    listen_future = listen_pool.submit(_listen_to_reels, reels, transcribe, heard_so_far)

    fake_result = analyze_fake_followers(
        profile["followers"], profile["following"], profile["posts"],
        profile["has_profile_pic"], profile["bio_length"],
        profile["has_external_url"], profile["is_private"],
        **name_features(profile.get("username"), profile.get("full_name")),
    )

    engagement_result = analyze_engagement(
        profile["followers"],
        engagement_data["avg_likes"],
        engagement_data["avg_comments"],
        profile["posts"],
        posts_analyzed=engagement_data.get("posts_analyzed"),
        comments_off=engagement_data.get("comments_off", False),
    )

    # ---- Comment Authenticity Check (uses most recent post) ----
    comment_authenticity = {
        "verdict": "No posts available",
        "comment_diversity_score": None,
        "campaign_keyword_detected": False,
    }
    try:
        post_codes = engagement_data.get("post_codes", [])
        if post_codes:
            comments = fetch_post_comments(post_codes[0])
            comment_authenticity = analyze_comment_authenticity(comments)
    except Exception:
        pass

    # ---- Credential Extraction & Confidence Scoring ----
    # Checked against the PMDC and US NPI doctor registers when the bio claims
    # to be a doctor; other credentials are reported but not scored.
    credential_result = calculate_credential_confidence(
        profile.get("biography", ""), profile["is_verified"],
        full_name=profile.get("full_name") or "",
    )

    # ---- Misinformation Classification (bio + post captions) ----
    # Every text goes through assess_text (the AI classifier cross-checked
    # against the rule-based red flags); the single riskiest one decides the
    # module, and every individual result is kept for the breakdown.
    misinfo_sources = []
    bio_text = profile.get("biography", "")
    if bio_text and bio_text.strip():
        try:
            r = assess_text(bio_text, classify_text)
            r["source"] = "bio"
            r["text_preview"] = bio_text[:80]
            misinfo_sources.append(r)
        except Exception as e:
            misinfo_sources.append({"status": "error", "message": str(e), "source": "bio"})

    for caption in engagement_data.get("post_captions", []):
        try:
            r = assess_text(caption, classify_text)
            r["source"] = "caption"
            r["text_preview"] = caption[:80]
            misinfo_sources.append(r)
        except Exception:
            pass  # one bad caption shouldn't break the whole scan

    # The submitted post's caption, if it isn't among the recent posts above.
    if focus and focus.get("caption") and focus.get("code") not in engagement_data.get("post_codes", []):
        try:
            r = assess_text(focus["caption"], classify_text)
            r["source"] = "caption"
            r["text_preview"] = focus["caption"][:80]
            r["submitted"] = True
            misinfo_sources.append(r)
        except Exception:
            pass

    # ---- Reel speech (Module 12) ----
    # Clear speech is checked exactly like a caption. Unclear speech (music,
    # noise) is shown on the Results page but never scored: measured, Whisper
    # can "hear" whole sentences in music.
    try:
        wait = max(0.5, REEL_TIME_BUDGET - (time.monotonic() - listen_started))
        heard = listen_future.result(timeout=wait)
    except FutureTimeout:
        heard = list(heard_so_far)
        done = {h["code"] for h in heard}
        heard += [dict(_reel_base(r), available=False, error=TIME_LIMIT_NOTE)
                  for r in reels if r["code"] not in done]
    finally:
        listen_pool.shutdown(wait=False)
    for h in heard:
        h["counted"] = False
        if not h.get("available"):
            h["not_counted_reason"] = h.get("error") or "couldn't listen to this reel"
        elif h.get("no_speech"):
            h["not_counted_reason"] = "no speech in this reel"
        elif not h.get("is_reliable"):
            h["not_counted_reason"] = "the speech was unclear, so it is shown but not scored"
        elif h.get("language") not in SCORED_LANGUAGES:
            h["not_counted_reason"] = (
                f"our misinformation model was only trained on English and Urdu, not "
                f"{h.get('language_name') or 'this language'}, so its verdict couldn't be trusted")
        else:
            try:
                r = assess_text(h["text"], classify_text)
            except Exception as e:
                r = {"status": "error", "message": str(e)}
            if r.get("status") == "success" and _unbacked_urdu_label(h, r):
                h["assessment"] = {k: r.get(k) for k in (
                    "primary_category", "misinformation_flag", "risk_score", "confidence",
                    "red_flags", "model_category", "note")}
                h["not_counted_reason"] = (
                    "the misinformation model gave this Urdu speech a warning label with no red flag "
                    "to back it; tested on ordinary Pakistani reels it does that to normal conversation, "
                    "so it is shown but not scored")
            elif r.get("status") == "success":
                r["source"] = "reel_speech"
                r["text_preview"] = h["text"][:80]
                r["reel_code"] = h["code"]
                misinfo_sources.append(r)
                h["counted"] = True
                h["assessment"] = {k: r.get(k) for k in (
                    "primary_category", "misinformation_flag", "risk_score", "confidence",
                    "red_flags", "model_category", "note")}
            else:
                h["not_counted_reason"] = "the misinformation model couldn't read this transcript"
    transcription = _transcription_section(reel_media, heard, focus)

    misinfo_result = worst(misinfo_sources)
    if misinfo_result is None:
        misinfo_result = {
            "status": "skipped",
            "message": "No bio, caption or clear reel speech was available to classify",
        }

    trust_result = calculate_trust_score(
        fake_result["bot_percentage"],
        engagement_result["engagement_score"],
        misinfo_result,
        credential_result,
    )

    result = {
        "username": profile["username"],
        "full_name": profile["full_name"],
        "is_verified": profile["is_verified"],
        "raw_profile_data": profile,
        "engagement_data": engagement_data,
        "fake_follower_analysis": fake_result,
        "engagement_analysis": engagement_result,
        "comment_authenticity": comment_authenticity,
        "credential_analysis": credential_result,
        "misinformation_analysis": misinfo_result,
        "misinformation_sources": misinfo_sources,
        "video_transcription": transcription,
        "trust_score": trust_result,
    }
    if focus:
        result["submitted_post"] = {
            "code": focus.get("code"),
            "url": f"https://www.instagram.com/{'reel' if focus.get('is_video') else 'p'}/{focus.get('code')}/",
            "is_video": focus.get("is_video"),
            "caption_preview": (focus.get("caption") or "")[:200],
            "like_count": focus.get("like_count"),
            "comment_count": focus.get("comment_count"),
        }
    return result


def save_scan(db, user_id, result, source="web"):
    """Store a finished result. Returns the ScanHistory row, or None if the
    save failed — a DB hiccup must never break a scan that already worked."""
    ts = result["trust_score"]
    try:
        scan = ScanHistory(
            user_id=user_id,
            username=result["username"],
            full_name=result["full_name"],
            is_verified=result["is_verified"],
            followers=(result.get("raw_profile_data") or {}).get("followers"),
            trust_score=ts["trust_score"],
            verdict=ts["verdict"],
            color=ts["color"],
            bot_percentage=result["fake_follower_analysis"].get("bot_percentage"),
            engagement_score=result["engagement_analysis"].get("engagement_score"),
            misinformation_flag=result["misinformation_analysis"].get("misinformation_flag"),
            raw_result=json.dumps(result),
            source=source if source in SOURCES else "web",
        )
        db.add(scan)
        db.commit()
        db.refresh(scan)
        return scan
    except Exception as e:
        db.rollback()
        print(f"Warning: could not save scan history: {e}")
        return None


def run_scan(db, user_id, username, source="web"):
    """Analyze, save, update the user's watchlist. Raises ScanFailed."""
    kind, value = parse_scan_input(username)
    if not kind:
        raise ScanFailed("Please provide a username or an Instagram link", "invalid")

    focus = None
    if kind == "post":
        # A post or reel link: find who posted it, then scan that account
        # with this post always included (scope: "pastes a profile or reel
        # link to receive an instant Trust Score report").
        owner = username_in_post_link(username)
        try:
            focus = fetch_media_data(value)
        except Exception as e:
            if not owner:
                raise ScanFailed(
                    f"Couldn't open that post or reel: {e} It may be private or deleted, or the "
                    "service may be busy. Try again in a minute, or scan the account by its "
                    "username or profile link.", "network")
            # The link names the account (instagram.com/<user>/reel/<code>),
            # so the account can still be scanned.
            focus = {"code": value, "username": owner, "code_only": True}
        if not focus.get("username"):
            raise ScanFailed("Couldn't tell who posted that post or reel.", "not_found")
        value = focus["username"]

    result = analyze_username(value, focus=focus)
    scan = save_scan(db, user_id, result, source)
    # Returned (not stored in raw_result) so the Results page can offer
    # "Report this score" against this exact saved record.
    result["scan_id"] = scan.id if scan else None
    result["scan_owned"] = bool(scan)

    if scan:
        # Imported here: watchlist imports this module for its re-checks.
        from watchlist import record_scan
        try:
            record_scan(db, user_id, scan)
        except Exception as e:  # monitoring must never break a scan
            print(f"Warning: watchlist update failed: {e}")
    return result
