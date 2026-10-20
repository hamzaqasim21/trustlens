# ============================================================
# TrustLens — the scan pipeline, in one place
# ============================================================
#
# Every way of scanning an account runs THIS function, so they can never
# disagree with each other:
#   - the Scan page and the Comparison page      (source "web")
#   - an automatic re-check of a watched account  (source "watchlist")
#
# It used to live inside main.py's /analyze-live handler; it was moved here
# unchanged when those other entry points were added, so each of them is a
# thin wrapper around the same real pipeline, not a copy of it.

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "misinfo_classifier", "api"))
from model_loader import classify_text  # noqa: E402

from fake_follower import analyze_fake_followers, name_features  # noqa: E402
from misinfo_assessment import assess_text, worst  # noqa: E402
from engagement_analyzer import analyze_engagement, analyze_comment_authenticity  # noqa: E402
from trust_score import calculate_trust_score  # noqa: E402
from data_ingestion import (  # noqa: E402
    fetch_instagram_profile, fetch_engagement_data, fetch_post_comments, ProfileNotFoundError,
)
from credential_extractor import calculate_credential_confidence  # noqa: E402
from database import ScanHistory  # noqa: E402

SOURCES = {"web", "watchlist"}


class ScanFailed(Exception):
    """A scan that could not produce a result. `kind` lets every caller tell
    "that account doesn't exist" (not_found) from "Instagram was slow" (network)."""

    def __init__(self, message, kind="network"):
        super().__init__(message)
        self.kind = kind


def analyze_username(username: str) -> dict:
    """Fetch the account and run all four modules. No database access."""
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

    misinfo_result = worst(misinfo_sources)
    if misinfo_result is None:
        misinfo_result = {
            "status": "skipped",
            "message": "No bio or caption text was available to classify",
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
        "trust_score": trust_result,
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
    username = (username or "").strip().lstrip("@")
    if not username:
        raise ScanFailed("Please provide a username", "invalid")

    result = analyze_username(username)
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
