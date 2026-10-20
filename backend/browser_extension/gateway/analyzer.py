"""
Verdict logic, how the raw module outputs become one badge on the screen.

This file holds the judgement calls, kept apart from the plumbing in clients.py
so the reasoning is reviewable in one place.

Two decisions drive everything here, and both come from the modules' own
measured weaknesses rather than from taste:

1. **The red-flag layer is trusted more than the category label.**
   The post checker's own evaluation shows the category model degrades badly on
   real caption text (health-misinformation recall 0.10, political propaganda
   over-firing on ordinary civic sentences) while staying ~0.85 confident, it is
   confidently wrong, not uncertain. Its red flags are pattern matches on what the
   text *does* (guaranteed returns, urgency, "DM me", pay-off-platform), which do
   not degrade the same way. So a category alone never raises the badge past
   "caution"; corroboration by red flags is what makes it a warning.

2. **Absent evidence is reported, never silently scored as innocent.**
   A reel whose audio could not be transcribed is "not checked", not "clean".
   Collapsing those two states is how a trust product ends up vouching for
   something it never looked at.
"""
from __future__ import annotations

# Badge levels, lowest to highest. The UI colours from these.
LEVEL_ORDER = ["unknown", "clean", "caution", "warning", "danger"]

_SEVERITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}

# Categories that mean "this text is claiming something harmful", as opposed to
# `credible`. Kept explicit so a model retrain that adds a class fails loudly here
# rather than silently mapping to "clean".
RISK_CATEGORIES = {
    "financial_scam": "Financial scam",
    "health_misinformation": "Health misinformation",
    "political_propaganda": "Political propaganda",
}

# Flag types, copied from the post checker's FLAG_SEVERITY table plus the two
# contributed by its link and claim checkers. Names must match exactly, a typo
# here silently downgrades a real scam, so they are asserted in the tests.
HIGH_FLAGS = {
    "financial_promise",     # "guaranteed profit", "300% returns"
    "health_claim",          # "cures diabetes" — the flag the category model misses
    "impossible_claim",      # arithmetic that cannot be true
    "link_risk",             # a link to a known-bad or disguised destination
    "prize_scam",            # "you have won a free iPhone, text WIN to 80082"
}

MEDIUM_FLAGS = {"urgency", "engagement_bait", "phone_number"}

# Flags too ordinary to mean anything alone, plenty of legitimate creators use
# link-in-bio and hashtags.
LOW_FLAGS = {"off_platform_contact", "hashtag_stuffing", "shouting", "link_pushing"}


def _worst(*levels: str) -> str:
    """Highest severity among the levels given."""
    return max(levels, key=lambda lv: LEVEL_ORDER.index(lv if lv in LEVEL_ORDER else "unknown"))


# Each level owns a slice of the 0-100 dial. The score is placed *inside* its
# level's band, so the number the ring shows can never disagree with the colour.
_SCORE_BANDS = {
    "danger":  (5, 22),
    "warning": (26, 45),
    "caution": (50, 68),
    "clean":   (82, 96),
}


def _trust_score(level: str, flags: list[dict], account: dict) -> int | None:
    """A 0-100 trust score for the badge ring, or None when nothing was checked.

    'unknown' means we did not actually read the thing, so it has no score:
    printing a number there would invent confidence we have not earned, which is
    the same false-reassurance trap the rest of this file exists to avoid. For
    every real level, more evidence against the post pushes the score toward the
    low end of that level's band.
    """
    if level not in _SCORE_BANDS:
        return None
    lo, hi = _SCORE_BANDS[level]

    pressure = sum(_SEVERITY_WEIGHT.get(f.get("severity", "low"), 1) for f in flags)
    severity = min(pressure, 8) / 8 * 0.7
    if account.get("available") and account.get("prob_fake") is not None:
        severity += float(account["prob_fake"]) * 0.3
    severity = max(0.0, min(1.0, severity))

    return int(round(hi - severity * (hi - lo)))


def _score_label(score: int | None) -> str:
    """One short word for the score, shown under the ring."""
    if score is None:
        return "Not scored"
    if score >= 80:
        return "Trusted"
    if score >= 60:
        return "Mostly clear"
    if score >= 40:
        return "Caution"
    if score >= 20:
        return "Risky"
    return "High risk"


def build_verdict(classification: dict, account: dict, transcript: dict,
                  text_used: str, text_sources: list[str],
                  is_reel: bool = False) -> dict:
    """Fuse the module outputs into one badge.

    Returns the payload the extension renders: a level, a headline, the evidence
    behind it, and an explicit list of what could not be checked.
    """
    reasons: list[str] = []       # short strings shown under the headline
    evidence: list[dict] = []     # structured, also fed to Gemini for the "Why?"
    not_checked: list[str] = []
    # A risky category with nothing concrete backing it. Reported as a footnote,
    # never as a reason, see the ladder below.
    uncorroborated_category: str | None = None

    # ------------------------------------------------------------------ #
    # Content signal
    # ------------------------------------------------------------------ #
    content_level = "unknown"
    category = None
    category_label = None
    confidence = 0.0
    risk_score = 0
    flags: list[dict] = []

    if classification.get("available"):
        category = classification.get("category")
        category_label = classification.get("category_label")
        confidence = float(classification.get("confidence") or 0.0)
        risk_score = int(classification.get("post_risk_score") or 0)
        flags = list(classification.get("red_flags") or [])
        low_margin = bool(classification.get("low_margin"))

        high_hits = [f for f in flags if f.get("type") in HIGH_FLAGS
                     or f.get("severity") == "high"]
        med_hits = [f for f in flags if f.get("type") in MEDIUM_FLAGS
                    and f not in high_hits]
        flag_pressure = sum(_SEVERITY_WEIGHT.get(f.get("severity", "low"), 1)
                            for f in flags)

        risky_category = category in RISK_CATEGORIES

        # ---- the ladder: red flags lead, the category only corroborates ---- #
        #
        # Measured on this very model with caption-register text:
        #   "Sunset at Hunza valley…"            -> financial_scam  @ 0.985
        #   "New winter collection, free delivery"-> financial_scam  @ 0.866
        #   "This root CURES diabetes…big pharma" -> credible        @ 0.995
        #
        # It is confidently wrong in *both* directions, so it cannot be allowed to
        # raise a badge by itself, and its `credible` cannot lower one. The red
        # flags are deterministic lexicon/'structure matches and do not have this
        # failure mode, so they carry the verdict.
        if len(high_hits) >= 2 or (high_hits and risky_category):
            content_level = "danger"
        elif high_hits:
            content_level = "warning"
        elif len(med_hits) >= 2 or flag_pressure >= 4:
            content_level = "caution"
        elif flags:
            content_level = "caution" if flag_pressure >= 3 else "clean"
        else:
            # No flags: clean regardless of what the category said.
            content_level = "clean"

        # Flags first: they are the evidence the verdict actually rests on, so
        # they are what the user should read at the top of the badge.
        for f in flags[:6]:
            reasons.append(f.get("title") or f.get("type", "flag"))
            evidence.append({
                "kind": "red_flag",
                "type": f.get("type"),
                "title": f.get("title"),
                "severity": f.get("severity"),
                "detail": f.get("detail", ""),
            })

        if risky_category:
            label = RISK_CATEGORIES[category]
            evidence.append({
                "kind": "category", "label": label,
                "confidence": round(confidence, 3), "low_margin": low_margin,
                "corroborated": bool(flags),
            })
            if flags:
                # Worth saying only when something concrete backs it up.
                reasons.append(f"The wording also matches {label.lower()}.")
            else:
                # Footnote, deliberately not a reason: this is the exact case
                # that called a sunset photo a financial scam at 0.985, so it
                # must never read as an accusation.
                uncorroborated_category = label

        # `credible` is not evidence of authenticity — the module README is
        # explicit about this, so say the useful thing instead.
        if content_level == "clean" and not flags:
            reasons.append("No scam patterns or manipulative language found in the text.")
    else:
        not_checked.append(
            f"Content: {classification.get('error', 'classifier unavailable')}"
        )

    # ------------------------------------------------------------------ #
    # Account signal
    # ------------------------------------------------------------------ #
    account_level = "unknown"
    prob_fake = None
    if account.get("available"):
        prob_fake = float(account.get("prob_fake") or 0.0)
        band = account.get("band", "uncertain")
        acct_conf = float(account.get("confidence") or 0.0)

        if band == "fake":
            account_level = "warning" if prob_fake >= 0.80 else "caution"
            reasons.append(
                f"The account profile looks bot-like ({prob_fake:.0%} likelihood)."
            )
        elif band == "uncertain":
            account_level = "caution"
            reasons.append("The account's stats are ambiguous — not clearly real or fake.")
        else:
            account_level = "clean"

        evidence.append({
            "kind": "account", "band": band,
            "prob_fake": round(prob_fake, 3), "confidence": round(acct_conf, 3),
        })
    else:
        not_checked.append(f"Account: {account.get('error', 'model unavailable')}")

    # ------------------------------------------------------------------ #
    # Transcript quality, affects how much the content signal is worth
    # ------------------------------------------------------------------ #
    if transcript:
        if transcript.get("available") and transcript.get("no_speech"):
            # Listened, and nobody talks (music, silence, or no audio track).
            # That is a real result, not a gap: there is no spoken pitch to miss.
            reasons.append("The audio was checked: no speech in it (music or silence)."
                           if not transcript.get("no_audio")
                           else "This video has no audio track, so there is nothing spoken to check.")
        elif transcript.get("available"):
            if not transcript.get("is_reliable", False):
                not_checked.append(
                    "The speech in this video was unclear (music or noise), so what "
                    "was heard is shown but not used to judge the post."
                )
            evidence.append({
                "kind": "transcript",
                "language": transcript.get("language"),
                "confidence": round(float(transcript.get("confidence") or 0.0), 3),
                "quality": transcript.get("quality"),
                "chars": transcript.get("char_count", 0),
            })
        else:
            not_checked.append(f"Spoken audio: {transcript.get('error', 'not transcribed')}")

    # ------------------------------------------------------------------ #
    # Combine
    # ------------------------------------------------------------------ #
    level = _worst(content_level, account_level)

    # No text at all means the content verdict is vacuous, whatever the modules
    # said. Never let an empty caption read as "clean" — "clean" ranks *above*
    # "unknown", so taking the worst of the two would report reassurance we did
    # not earn. Only a genuinely alarming account signal survives here.
    if not (text_used or "").strip():
        level = account_level if account_level in ("caution", "warning", "danger") \
            else "unknown"
        not_checked.append("No caption or spoken text was found to analyse.")

    # A reel whose speech was never transcribed has not really been read. Its
    # caption and on-screen text are a fraction of the content, a scam pitched
    # out loud is invisible to everything above. A green "Nothing suspicious
    # found" there is false reassurance, so a reassuring verdict is downgraded to
    # "not checked".
    #
    # Only the *reassuring* direction is downgraded. If flags already fired, the
    # evidence is real and the warning stands, hearing the audio could only make
    # it worse, never better.
    # "Read" means the audio was actually checked — including a check that
    # found no speech at all, which is a finding, not a gap.
    speech_read = "speech" in (text_sources or []) or bool(
        transcript and transcript.get("available"))
    if is_reel and not speech_read and level in ("clean", "unknown"):
        level = "unknown"
        partial_reel = True
    else:
        partial_reel = False

    # Only a *corroborated* risky category may name the headline. Without this
    # guard a post flagged by its red flags while the model said `credible`
    # would be headlined "Possible credible".
    headline_label = (RISK_CATEGORIES.get(category)
                      if (category in RISK_CATEGORIES and flags) else None)
    headline = _headline(level, headline_label, prob_fake, flags)
    if partial_reel:
        # Say what *was* read, not only what was not. The old wording
        # ("Spoken audio not checked yet") paired with the "Not fully checked"
        # level label to read as "Not fully checked - not checked yet", which
        # told the viewer nothing on the one line they actually see.
        headline = ("Caption read, audio not heard"
                    if (text_used or "").strip()
                    else "Nothing readable yet, audio not heard")
        # The clean-text reason reads as an all-clear on its own. Replace it with
        # one that says exactly how far the check got.
        reasons = [r for r in reasons
                   if not r.startswith("No scam patterns")]
        reasons.insert(0, "Only the caption and on-screen text were read — "
                          "nobody has listened to what is said in this video.")

    notes: list[str] = []
    if uncorroborated_category:
        notes.append(
            f"The language model also labelled this text "
            f"'{uncorroborated_category}', but nothing concrete in the post "
            f"supports that, so it was not counted. This label is unreliable on "
            f"ordinary captions."
        )

    score = _trust_score(level, flags, account)

    return {
        "level": level,
        "score": score,
        "score_label": _score_label(score),
        "headline": headline,
        "reasons": reasons[:8],
        "notes": notes,
        "evidence": evidence,
        "not_checked": not_checked,
        "content": {
            "level": content_level,
            "category": category,
            "category_label": category_label,
            "category_counted": bool(category in RISK_CATEGORIES and flags),
            "confidence": round(confidence, 3),
            "risk_score": risk_score,
            "red_flag_count": len(flags),
            "red_flags": flags,
        },
        "account": {
            "level": account_level,
            "prob_fake": prob_fake,
            "band": account.get("band") if account.get("available") else None,
        },
        # What was actually read. The UI uses this to decide whether to offer the
        # "Listen to audio" button and how strongly to word the badge.
        "coverage": {
            "is_reel": is_reel,
            "speech_read": speech_read,
            "account_read": bool(account.get("available")),
            "partial": partial_reel,
        },
        "text_analyzed": text_used,
        "text_sources": text_sources,
    }


# When no category is available to name the risk, the top red flag describes it
# better than a generic "Suspicious" would.
_FLAG_HEADLINE = {
    "financial_promise": "money-making claims",
    "health_claim": "unsupported health claims",
    "impossible_claim": "claims that cannot be true",
    "link_risk": "a suspicious link",
    "prize_scam": "a fake prize or lottery win",
    "phone_number": "a phone number to contact",
    "urgency": "pressure tactics",
    "engagement_bait": "engagement bait",
}


def _headline(level: str, category_label: str | None, prob_fake: float | None,
              flags: list[dict] | None = None) -> str:
    top = None
    for f in (flags or []):
        if f.get("type") in _FLAG_HEADLINE:
            top = _FLAG_HEADLINE[f["type"]]
            break

    if level == "danger":
        if category_label:
            return f"Likely {category_label.lower()}"
        return f"High risk — {top}" if top else "High risk"
    if level == "warning":
        if category_label:
            return f"Possible {category_label.lower()}"
        if top:
            return f"Contains {top}"
        if prob_fake is not None and prob_fake >= 0.8:
            return "Bot-like account"
        return "Suspicious"
    if level == "caution":
        return "Worth a second look"
    if level == "clean":
        return "Nothing suspicious found"
    return "Not enough to judge"
