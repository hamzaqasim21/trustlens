# ============================================================
# TrustLens — Score confidence and the "Requires Further Review" label
# ============================================================
#
# Scope document, Ethical Considerations:
#   "Confidence Display: Every score is accompanied by a confidence
#    percentage. Scores below 60% confidence are marked as Uncertain and the
#    user is advised not to draw firm conclusions."
#   "Human-in-the-Loop for Borderline Cases: Scores between 35 and 55 trigger
#    a Requires Further Review label rather than a definitive verdict."
#
# WHAT THIS CONFIDENCE IS, HONESTLY
# ---------------------------------
# It is NOT a calibrated statistical probability that the verdict is right
# (that would need a large labelled set of real influencer verdicts, which
# does not exist). It is a transparent, rule-based measure of two things we
# can actually observe for every scan:
#
#   1. How sure each module was about ITS OWN answer ("certainty"), and
#   2. How much of the evidence we wanted we actually got ("coverage").
#
#   confidence = (weighted average of module certainties) x coverage
#
# The weights are the same ones the Trust Score used for this scan, so a
# module that moved the score a lot also moves the confidence a lot. Every
# factor is returned with a plain-language note, so the number can always be
# explained line by line.

# The scope document's base weights (same as trust_score.BASE_WEIGHTS).
from trust_score import BASE_WEIGHTS

UNCERTAIN_BELOW = 60        # scope: "below 60% confidence ... Uncertain"
REVIEW_LOW, REVIEW_HIGH = 35, 55   # scope: "Scores between 35 and 55"

# Credential register outcomes and how sure a name lookup can be about them.
# A single exact match on an official register is strong; several doctors
# sharing the name, or no match at all (spelling, maiden names, a register
# not covering that country), is weaker.
_CREDENTIAL_CERTAINTY = {
    "found_active": 0.9,
    "found_inactive": 0.8,
    "not_found": 0.7,
}


def _fake_follower_certainty(ff):
    """The Random Forest's probability of 'fake'. 50% is a coin flip (no
    certainty); 0% or 100% is fully certain either way."""
    p = (ff or {}).get("bot_percentage")
    if p is None:
        return None, "Fake-account check did not run"
    c = abs(p - 50) / 50
    return c, f"The fake-account model gave {p}% (the further from 50%, the surer it is)"


def _engagement_certainty(eng, engagement_data):
    posts = (engagement_data or {}).get("posts_analyzed") or 0
    if (eng or {}).get("engagement_score") is None or posts == 0:
        return None, "No posts could be read, so engagement wasn't measured"
    c = min(posts, 12) / 12
    return c, f"Averaged over {posts} of the 12 recent posts we ask for"


def _misinfo_certainty(mi, sources):
    if (mi or {}).get("status") != "success":
        return None, "No bio or caption text was available to check"
    n = len([s for s in (sources or []) if s.get("status") == "success"])
    if mi.get("corroborated"):
        return 0.95, (f"Decided by a concrete scam pattern found in the text "
                      f"({n} text{'s' if n != 1 else ''} checked)")
    conf = mi.get("confidence")
    if conf is None:
        return 0.5, f"{n} text{'s' if n != 1 else ''} checked"
    return float(conf), (f"The classifier was {round(conf * 100)}% sure about the text that "
                         f"decided this module ({n} text{'s' if n != 1 else ''} checked)")


def _credential_certainty(cred):
    if not cred or cred.get("confidence_score") is None:
        return None, None
    v = cred.get("verification") or {}
    status = v.get("status")
    c = _CREDENTIAL_CERTAINTY.get(status, 0.6)
    if status == "found_active" and (v.get("match_count") or 0) > 1:
        c = 0.6
        return c, f"{v.get('match_count')} registered doctors share this name"
    return c, {
        "found_active": "Exact name match on an official register",
        "found_inactive": "Exact name match, but the licence isn't active",
        "not_found": "Name not found; a spelling difference can cause this",
    }.get(status, "Checked against a register")


def assess_confidence(result: dict) -> dict:
    """Takes a full /analyze-live result and returns the confidence block.
    Works on old saved scans too (it only reads fields every scan has)."""
    ts = result.get("trust_score") or {}
    weights = ts.get("weights_used") or {}
    score = ts.get("trust_score")

    per_module = {
        "fake_follower": _fake_follower_certainty(result.get("fake_follower_analysis")),
        "engagement": _engagement_certainty(result.get("engagement_analysis"),
                                            result.get("engagement_data")),
        "misinformation": _misinfo_certainty(result.get("misinformation_analysis"),
                                             result.get("misinformation_sources")),
        "credential": _credential_certainty(result.get("credential_analysis")),
    }

    factors = []
    weighted, total_w = 0.0, 0.0
    for module, (certainty, note) in per_module.items():
        if certainty is None or module not in weights:
            continue
        w = weights[module]
        weighted += certainty * w
        total_w += w
        factors.append({"module": module, "certainty": round(certainty * 100),
                        "weight": w, "note": note})
    certainty = weighted / total_w if total_w else 0.0

    # Coverage: evidence we wanted but could not get. A module that had
    # nothing to judge (no credential claimed at all) is not missing data;
    # one that should have run but couldn't (no posts readable, no text,
    # a claim the registers couldn't be reached for) is.
    missing = []
    if per_module["engagement"][0] is None:
        missing.append(("engagement", per_module["engagement"][1]))
    if per_module["misinformation"][0] is None:
        missing.append(("misinformation", per_module["misinformation"][1]))
    cred = result.get("credential_analysis") or {}
    if cred.get("claims_found") and (cred.get("verification") or {}).get("status") == "unavailable":
        missing.append(("credential", "A credential was claimed but the registers couldn't be reached"))

    present_w = sum(BASE_WEIGHTS[m] for m in weights if m in BASE_WEIGHTS)
    missing_w = sum(BASE_WEIGHTS[m] for m, _ in missing)
    coverage = present_w / (present_w + missing_w) if present_w + missing_w else 0.0

    confidence = round(100 * certainty * coverage)
    if confidence >= 80:
        label = "High"
    elif confidence >= UNCERTAIN_BELOW:
        label = "Medium"
    else:
        label = "Uncertain"

    needs_review = score is not None and REVIEW_LOW <= score <= REVIEW_HIGH

    return {
        "confidence": confidence,
        "label": label,
        "uncertain": confidence < UNCERTAIN_BELOW,
        "certainty": round(certainty * 100),
        "coverage": round(coverage * 100),
        "factors": factors,
        "missing": [{"module": m, "note": n} for m, n in missing],
        "needs_review": needs_review,
        "review_note": (
            f"Scores between {REVIEW_LOW} and {REVIEW_HIGH} are borderline, so this is marked "
            "Requires Further Review rather than a firm verdict. Look at the breakdown and "
            "decide for yourself."
        ) if needs_review else None,
        "method": ("Rule-based: average certainty of each module (weighted like the score) "
                   "x share of the evidence that was available. Not a calibrated probability."),
    }
