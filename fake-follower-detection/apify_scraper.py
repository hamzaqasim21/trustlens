"""
Fetch a public Instagram profile through Apify and map it to the 7 raw features.
Reads the API token from the APIFY_API_TOKEN environment variable.
"""
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from predict_core import username_digit_ratio, RAW_FEATURES

PROFILE_SCRAPER_ACTOR = "apify/instagram-profile-scraper"

CACHE_DIR = Path(__file__).parent / "cache"

# Instagram paths that are app sections rather than usernames
_RESERVED_PATHS = {
    "p", "reel", "reels", "tv", "stories", "explore",
    "accounts", "direct", "about", "developer", "legal", "privacy",
}


def extract_username(raw: str) -> str:
    """Accept a username, '@username' or a profile URL and return the username."""
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Please enter a username or profile URL.")

    if "instagram.com" in raw.lower():
        url = raw if raw.startswith(("http://", "https://")) else f"https://{raw}"
        segment = urlparse(url).path.strip("/").split("/")[0]
        if not segment or segment.lower() in _RESERVED_PATHS:
            raise ValueError(
                "That looks like an Instagram link but not a profile link "
                "(e.g. a post/reel URL). Paste the profile URL or just the username."
            )
        return segment.lstrip("@").lower()

    return raw.lstrip("@").lower()


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
    """Run the Apify actor and return the raw profile JSON.

    Results are cached to cache/<username>.json to avoid repeat API calls.
    """
    username = extract_username(username)
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{username}.json"

    if use_cache and cache_file.exists():
        with open(cache_file, encoding="utf-8") as f:
            return json.load(f)

    from apify_client import ApifyClient

    client = ApifyClient(_get_token(token))
    run_input = {"usernames": [username]}
    run = client.actor(PROFILE_SCRAPER_ACTOR).call(run_input=run_input)
    if run is None:
        raise RuntimeError("Apify actor did not finish (timed out or failed to start).")

    # apify-client 3.x returns a Run object; older versions returned a dict
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
    """First non-None value among the given keys."""
    for k in keys:
        if k in profile and profile[k] is not None:
            return profile[k]
    return default


def profile_to_raw_features(profile: dict) -> dict:
    """Map the Apify profile JSON to the 7 raw features."""
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
    assert set(raw) == set(RAW_FEATURES)
    return raw


def profile_summary(profile: dict) -> dict:
    """Display fields, not used by the model."""
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
