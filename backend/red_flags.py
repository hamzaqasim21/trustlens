"""
Rule-based red-flag detection for post captions and reel transcripts.

WHAT THIS IS, HONESTLY
----------------------
This is **pattern matching, not machine learning**. Every flag below is a
hand-written regular expression. It must never be presented as AI. That is
deliberate, and it is the whole reason this layer exists.

WHY IT EXISTS
-------------
`analyzer.py` trusts this layer *more* than the category model, and explains
why in its own docstring: the classifier degrades badly on real caption text
(health-misinformation recall 0.10, political propaganda over-firing on
ordinary civic sentences) while still reporting ~0.85 confidence. It is
confidently wrong rather than uncertain, which is the worst failure mode for
a trust product.

Red flags do not degrade that way, because they match on what the text
literally *does* — promises a guaranteed return, pushes an off-platform
contact, shouts — rather than on what a model thinks the text is about. A
regex for "guaranteed profit" either matches or it does not.

So: the classifier says what a post is *about*; this says what it is *doing*.
A risky category alone never raises the badge past "caution". Corroboration
from these flags is what turns it into a warning.

FLAG NAMES ARE A CONTRACT
-------------------------
The names below must match `analyzer.py`'s HIGH_FLAGS / MEDIUM_FLAGS /
LOW_FLAGS sets exactly. A typo silently downgrades a real scam instead of
failing loudly, so `test_red_flags.py` asserts them against those sets.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# Severity is a property of the flag type, not of the individual match.
# Mirrors the post checker's FLAG_SEVERITY table that analyzer.py expects.
# --------------------------------------------------------------------------- #
FLAG_SEVERITY = {
    # High — concrete, hard to say by accident.
    "financial_promise": "high",
    "health_claim": "high",
    "impossible_claim": "high",
    "link_risk": "high",
    "prize_scam": "high",
    # Medium — pressure tactics. Common in scams, occasionally legitimate.
    "urgency": "medium",
    "engagement_bait": "medium",
    "phone_number": "medium",
    # Low — ordinary creator behaviour. Meaningless alone, context when stacked.
    "off_platform_contact": "low",
    "hashtag_stuffing": "low",
    "shouting": "low",
    "link_pushing": "low",
}

FLAG_TITLE = {
    "financial_promise": "Guaranteed financial return",
    "health_claim": "Unproven health claim",
    "impossible_claim": "Mathematically impossible claim",
    "link_risk": "Risky or disguised link",
    "prize_scam": "Fake prize or lottery win",
    "urgency": "Artificial urgency",
    "engagement_bait": "Engagement bait",
    "phone_number": "Contact number in caption",
    "off_platform_contact": "Pushes contact off-platform",
    "hashtag_stuffing": "Hashtag stuffing",
    "shouting": "Excessive capitals",
    "link_pushing": "Link promotion",
}


# --------------------------------------------------------------------------- #
# Patterns
#
# Written to favour precision over recall on purpose. A false positive here
# escalates a badge on an innocent creator's post, which is the failure people
# actually notice and lose trust over. Missing a subtle scam is the cheaper
# error, because the category model is still watching in parallel.
# --------------------------------------------------------------------------- #
_PATTERNS: dict[str, list[str]] = {
    "financial_promise": [
        r"\bguarantee(?:d|s)?\s+(?:\w+\s+){0,2}?(?:profit|return|income|roi|money|payout)",
        r"\b\d{2,}\s*%\s*(?:guaranteed\s*)?(?:return|profit|gain|roi|monthly|weekly|daily)",
        r"\bdouble\s+your\s+(?:money|investment|capital|deposit)",
        r"\brisk[\s\-]?free\s+(?:invest|trading|profit|return|money)",
        r"\bno\s+risk\b.{0,20}\b(?:profit|return|guaranteed)",
        r"\b(?:guaranteed|assured)\s+(?:daily|weekly|monthly)\s+(?:payout|earning)",
    ],
    "health_claim": [
        # Naming a specific condition is what separates a real claim from
        # ordinary wellness talk ("good for your health" stays unflagged).
        r"\b(?:cure|cures|cured|reverse|reverses|heal|heals)\b.{0,30}?"
        r"\b(?:diabetes|cancer|arthritis|asthma|autism|alzheimer'?s?|hiv|aids|covid|tumou?r)",
        r"\bmiracle\s+(?:cure|remedy|drug|treatment|herb|root)",
        r"\bdoctors?\s+(?:hate|don'?t\s+want|won'?t\s+tell)",
        r"\bbig\s+pharma\b",
        r"\bcures?\s+(?:everything|anything|all\s+(?:diseases?|illness))",
        r"\b100\s*%\s*(?:natural\s+)?cure",
        r"\bdetox(?:ify|ifies)?\s+your\s+(?:body|liver|blood|gut)",
    ],
    "impossible_claim": [
        # Arithmetic that cannot be true, rather than merely optimistic.
        r"\b(?:[1-9]\d{2,})\s*%\s*(?:guaranteed|return|profit|gain)",
        r"\blose\s+\d{2,}\s*(?:kg|kgs|kilos?|pounds?|lbs)\s+in\s+\d+\s*(?:day|days|week)",
        r"\b(?:overnight|in\s+24\s*hours?|in\s+one\s+day)\b.{0,25}\b(?:millionaire|rich|\$\s*\d)",
        r"\bearn\s+\$?\s*\d{4,}\s*(?:per|a|every)\s*day\b",
        r"\bzero\s+effort\b.{0,20}\b(?:income|profit|money)",
    ],
    "link_risk": [
        # URL shorteners hide the destination, which is the point of using one
        # in a scam. Legitimate brands rarely need them in an IG caption.
        r"\b(?:bit\.ly|tinyurl\.com|goo\.gl|t\.me|cutt\.ly|rb\.gy|is\.gd|ow\.ly|shorturl\.at|rebrand\.ly)\b",
        # Free TLDs overwhelmingly used for throwaway phishing domains.
        r"https?://[^\s]*\.(?:tk|ml|ga|cf|gq)\b",
        # A bare IP address instead of a domain name.
        r"https?://\d{1,3}(?:\.\d{1,3}){3}\b",
    ],
    "prize_scam": [
        # The unsolicited "you have won" message. Ordinary giveaway posts
        # ("tag 2 friends to win", "@sara won our giveaway") are phrased
        # differently and are deliberately not matched.
        r"\byou(?:'ve|\s+have)\s+(?:just\s+)?(?:been\s+selected\s+(?:to\s+win|for)|won)\b.{0,30}?"
        r"\b(?:free|prize|cash|iphone|lottery|jackpot|gift\s*card|voucher|reward|\$\s*\d|rs\.?\s*\d)",
        # Premium-rate SMS: "text WIN to 80082".
        r"\b(?:text|sms)\s+[\"']?[a-z]{2,10}[\"']?\s+to\s+\d{4,6}\b",
        # Advance-fee: you must pay before the "prize" is released.
        r"\bpay\s+(?:a\s+|the\s+)?(?:small\s+)?(?:fee|tax|charges?)\s+to\s+(?:claim|receive|release|collect)",
        r"\b(?:lottery|jackpot)\s+winner\b",
    ],
    "urgency": [
        r"\b(?:act|buy|invest|join|sign\s*up)\s+now\b",
        r"\b(?:limited|last)\s+(?:time|chance|spots?|slots?|seats?)\b",
        r"\bonly\s+\d+\s+(?:left|remaining|spots?|slots?)\b",
        r"\b(?:hurry|don'?t\s+miss\s+out)\b",
        r"\bexpires?\s+(?:today|tonight|soon|in\s+\d+)",
        r"\b(?:today|tonight)\s+only\b",
    ],
    "engagement_bait": [
        r"\bcomment\s+(?:[\"']?\w+[\"']?)\s+(?:to|for|and)\b",
        r"\btag\s+\d+\s+(?:friends?|people)",
        r"\bdouble\s+tap\s+if\b",
        r"\b(?:share|repost)\s+to\s+(?:win|enter)",
        r"\bfollow\s+(?:me\s+)?to\s+(?:win|enter|get)",
        r"\blike\s+(?:and|&)\s+share\b",
    ],
    "phone_number": [
        # International format, long enough not to catch years or prices.
        r"(?:\+|00)\d{1,3}[\s\-]?\d{3}[\s\-]?\d{3,4}[\s\-]?\d{3,4}",
        r"\bwhats\s?app\b.{0,15}?\d{7,}",
    ],
    "off_platform_contact": [
        r"\b(?:dm|pm|inbox)\s+(?:me|us)\b",
        r"\b(?:message|msg)\s+(?:me|us)\s+on\b",
        r"\b(?:whats\s?app|telegram|signal)\s+(?:me|us|only)\b",
        r"\bcontact\s+(?:me|us)\s+(?:on|via|at)\b",
    ],
    "link_pushing": [
        r"\blink\s+in\s+(?:bio|comments?|story)\b",
        r"\bswipe\s+up\b",
        r"\bclick\s+(?:the\s+)?link\b",
        r"\bcheck\s+(?:out\s+)?(?:my|the)\s+link\b",
    ],
}

_COMPILED = {
    flag: [re.compile(p, re.IGNORECASE) for p in patterns]
    for flag, patterns in _PATTERNS.items()
}

# Thresholds for the two flags that are counted rather than matched.
HASHTAG_STUFFING_MIN = 8
SHOUTING_MIN_WORDS = 6
SHOUTING_CAPS_RATIO = 0.4

_HASHTAG_RE = re.compile(r"#\w+")
_WORD_RE = re.compile(r"\b[A-Za-z]{3,}\b")


def _regex_flags(text: str) -> list[dict]:
    found = []
    for flag, patterns in _COMPILED.items():
        matches: list[str] = []
        for pattern in patterns:
            matches.extend(m.group(0).strip() for m in pattern.finditer(text))

        if matches:
            # Deduplicate while keeping order, so "detail" reads naturally
            # instead of repeating the same phrase five times.
            seen, unique = set(), []
            for m in matches:
                key = m.lower()
                if key not in seen:
                    seen.add(key)
                    unique.append(m)

            found.append({
                "type": flag,
                "title": FLAG_TITLE[flag],
                "severity": FLAG_SEVERITY[flag],
                "detail": "matched: " + ", ".join(f'"{m}"' for m in unique[:3]),
                "match_count": len(matches),
            })
    return found


def _hashtag_stuffing(text: str) -> dict | None:
    tags = _HASHTAG_RE.findall(text)
    if len(tags) < HASHTAG_STUFFING_MIN:
        return None
    return {
        "type": "hashtag_stuffing",
        "title": FLAG_TITLE["hashtag_stuffing"],
        "severity": FLAG_SEVERITY["hashtag_stuffing"],
        "detail": f"{len(tags)} hashtags in one caption",
        "match_count": len(tags),
    }


def _shouting(text: str) -> dict | None:
    """Flags sustained ALL-CAPS, not the occasional emphasised word.

    Words shorter than three letters are ignored so ordinary acronyms (UK, AI,
    DM) do not drag the ratio up on an otherwise normal caption.
    """
    words = _WORD_RE.findall(text)
    if len(words) < SHOUTING_MIN_WORDS:
        return None

    caps = [w for w in words if w.isupper()]
    ratio = len(caps) / len(words)
    if ratio < SHOUTING_CAPS_RATIO:
        return None

    return {
        "type": "shouting",
        "title": FLAG_TITLE["shouting"],
        "severity": FLAG_SEVERITY["shouting"],
        "detail": f"{ratio:.0%} of words are in capitals",
        "match_count": len(caps),
    }


def detect_red_flags(text: str) -> list[dict]:
    """Returns every red flag found in `text`.

    Each flag carries the keys analyzer.py reads: type, title, severity,
    detail, match_count. Order is high severity first so that anything
    truncating the list for display keeps the important ones.
    """
    if not text or not text.strip():
        return []

    flags = _regex_flags(text)

    for extra in (_hashtag_stuffing(text), _shouting(text)):
        if extra:
            flags.append(extra)

    order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: (order[f["severity"]], f["type"]))
    return flags


def flag_pressure(flags: list[dict]) -> int:
    """Weighted total of the flags, used to lift the risk score.

    Same weights analyzer.py uses for its own ladder, kept consistent so the
    number shown to the user and the badge level cannot tell different stories.
    """
    weights = {"high": 3, "medium": 2, "low": 1}
    return sum(weights[f["severity"]] for f in flags)
