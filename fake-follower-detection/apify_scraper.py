"""
TrustLens - Fake Follower Detection
Fetch a public Instagram profile's raw attributes via Apify.

Uses Apify's official "Instagram Profile Scraper" actor
(apify/instagram-profile-scraper) and maps its output onto the exact 7 raw
features the model was trained on.

The Apify token is read from the APIFY_API_TOKEN environment variable
(never hard-coded). Set it once per terminal session:

    Windows PowerShell:   $env:APIFY_API_TOKEN = "apify_api_xxx"
    Windows CMD:          set APIFY_API_TOKEN=apify_api_xxx
    macOS/Linux:          export APIFY_API_TOKEN=apify_api_xxx
"""
import json
import os
from pathlib import Path

from predict_core import username_digit_ratio, RAW_FEATURES

# Apify's dedicated, low-cost Instagram profile scraper.
PROFILE_SCRAPER_ACTOR = "apify/instagram-profile-scraper"

CACHE_DIR = Path(__file__).parent / "cache"


def _get_token(token: str | None) -> str:
    token = token or os.environ.get("APIFY_API_TOKEN")
    if not token:
        raise RuntimeError(
            "No Apify token found.\n"
            "  Set it first:  $env:APIFY_API_TOKEN = \"apify_api_xxx\"   (PowerShell)\n"
            "  or pass token=... to scrape_profile()."
        )
    return token


def scrape_profile(username: str, token: str | None = None,
                   use_cache: bool = True) -> dict:
    """Run the Apify actor for one username and return the raw profile JSON.

    Results are cached to cache/<username>.json so the demo can be re-run
    instantly (and offline) without spending Apify credits again.
    """
    username = username.lstrip("@").strip().lower()
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{username}.json"

    if use_cache and cache_file.exists():
        with open(cache_file, encoding="utf-8") as f:
            return json.load(f)

    # Import here so the rest of the module works even without apify_client.
    from apify_client import ApifyClient

    client = ApifyClient(_get_token(token))
    run_input = {"usernames": [username]}
    run = client.actor(PROFILE_SCRAPER_ACTOR).call(run_input=run_input)
    if run is None:
        raise RuntimeError("Apify actor did not finish (timed out or failed to start).")

    # apify-client >= 3 returns a pydantic Run object (run.default_dataset_id);
    # older versions returned a plain dict (run["defaultDatasetId"]). Support both.
    dataset_id = getattr(run, "default_dataset_id", None)
    if dataset_id is None and isinstance(run, dict):
        dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        raise RuntimeError("Could not locate the Apify run's default dataset id.")

    items = list(client.dataset(dataset_id).iterate_items())

    if not items:
        raise RuntimeError(
            f"Apify returned no data for @{username}. "
            "The account may not exist, be banned, or be temporarily unavailable."
        )

    profile = items[0]
    if profile.get("error") or profile.get("followersCount") is None:
        raise RuntimeError(
            f"Could not read @{username}: "
            f"{profile.get('error', 'no follower data returned')}."
        )

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
    return profile


def _first(profile: dict, *keys, default=None):
    """Return the first present, non-None value among several possible keys.
    Makes the mapping robust to small differences between Apify actor versions."""
    for k in keys:
        if k in profile and profile[k] is not None:
            return profile[k]
    return default


def profile_to_raw_features(profile: dict) -> dict:
    """Map Apify's profile JSON -> the 7 raw features the model expects.

    Tolerant of alternate field names so the live demo does not break if the
    actor output schema shifts slightly (followersCount vs followers, etc.)."""
    username = _first(profile, "username", "ownerUsername", default="") or ""
    biography = _first(profile, "biography", "bio", default="") or ""
    profile_pic_url = _first(profile, "profilePicUrl", "profilePicUrlHD",
                             "profile_pic_url", default="") or ""
    is_private = _first(profile, "private", "isPrivate", "is_private", default=False)

    raw = {
        "profile_pic": 1 if profile_pic_url else 0,
        "username_digit_ratio": round(username_digit_ratio(username), 6),
        "description_length": len(biography),
        "private": 1 if is_private else 0,
        "posts_count": int(_first(profile, "postsCount", "posts", "mediaCount", default=0) or 0),
        "followers_count": int(_first(profile, "followersCount", "followers", default=0) or 0),
        "follows_count": int(_first(profile, "followsCount", "following", "follows", default=0) or 0),
    }
    # sanity: make sure every expected key is present
    assert set(raw) == set(RAW_FEATURES)
    return raw


def profile_summary(profile: dict) -> dict:
    """A few human-friendly fields for display (not used by the model)."""
    return {
        "username": profile.get("username", ""),
        "full_name": profile.get("fullName", ""),
        "verified": bool(profile.get("verified")),
        "is_business": bool(profile.get("isBusinessAccount")),
        "profile_pic_url": profile.get("profilePicUrl") or profile.get("profilePicUrlHD") or "",
        "biography": profile.get("biography", "") or "",
        "external_url": profile.get("externalUrl", "") or "",
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python apify_scraper.py <username>")
        raise SystemExit(1)
    prof = scrape_profile(sys.argv[1])
    print(json.dumps(profile_to_raw_features(prof), indent=2))
