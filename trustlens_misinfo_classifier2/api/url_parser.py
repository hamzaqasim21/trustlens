"""
url_parser.py
-------------
Turns whatever the user pastes — a profile URL, a post/reel URL, or
just a bare username — into a structured {type, value} so the fetch
layer knows what to do with it.

Examples handled:
    https://www.instagram.com/someuser/              -> profile, "someuser"
    https://www.instagram.com/someuser                -> profile, "someuser"
    instagram.com/someuser/                           -> profile, "someuser"
    https://www.instagram.com/p/Cabc123XyZ/           -> post, "Cabc123XyZ"
    https://www.instagram.com/reel/Cabc123XyZ/        -> post, "Cabc123XyZ"
    someuser                                          -> profile, "someuser"
"""

import re

NON_USERNAME_PATHS = {"p", "reel", "reels", "tv", "stories", "explore", ""}


def parse_instagram_input(raw: str) -> dict:
    raw = raw.strip()
    if not raw:
        return {"type": "invalid", "value": None}

    # Not a URL at all -> treat as a bare username
    if "instagram.com" not in raw:
        username = raw.lstrip("@").strip("/")
        return {"type": "profile", "value": username}

    # Strip protocol/query/fragment, split into path segments
    cleaned = re.sub(r"^(https?://)?(www\.)?instagram\.com/?", "", raw)
    cleaned = cleaned.split("?")[0].split("#")[0]
    parts = [p for p in cleaned.split("/") if p]

    if not parts:
        return {"type": "invalid", "value": None}

    if parts[0] in ("p", "tv") and len(parts) >= 2:
        return {"type": "post", "value": parts[1], "media_type": "post"}

    if parts[0] in ("reel", "reels") and len(parts) >= 2:
        return {"type": "post", "value": parts[1], "media_type": "reel"}

    if parts[0] in NON_USERNAME_PATHS:
        return {"type": "invalid", "value": None}

    # Otherwise first path segment is a username
    return {"type": "profile", "value": parts[0]}