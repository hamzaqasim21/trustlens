"""
Tests for the verdict logic.

These lock in the judgement calls documented in analyzer.py, particularly the
two that are easy to regress: a weak category must not alone produce a warning,
and an unchecked signal must never read as a clean one.

Run:  python -m pytest test_analyzer.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from analyzer import build_verdict  # noqa: E402


def flag(type_="financial_promise", severity="high", title="Financial promises"):
    return {"type": type_, "severity": severity, "title": title,
            "detail": 'matched: "guaranteed profit"', "match_count": 2}


def classification(available=True, category="credible", confidence=0.9,
                   flags=None, risk=10, low_margin=False):
    return {
        "available": available, "category": category,
        "category_label": category.replace("_", " ").title(),
        "confidence": confidence, "post_risk_score": risk,
        "red_flags": flags or [], "low_margin": low_margin,
    }


def account(available=True, band="real", prob_fake=0.1, confidence=0.9):
    return {"available": available, "band": band, "prob_fake": prob_fake,
            "confidence": confidence}


UNAVAILABLE = {"available": False, "error": "service down"}


# --------------------------------------------------------------------------- #
# The headline behaviours
# --------------------------------------------------------------------------- #
def test_scam_category_with_hard_flag_is_danger():
    v = build_verdict(
        classification(category="financial_scam", confidence=0.99, flags=[flag()], risk=100),
        account(), {}, "GUARANTEED PROFIT 300% returns", ["caption"],
    )
    assert v["level"] == "danger"
    assert "financial scam" in v["headline"].lower()


def test_uncorroborated_category_never_raises_the_badge():
    """Measured on this model with caption text: a sunset photo was called
    financial_scam at 0.985 and a shop's 'free delivery' post at 0.866. A
    category with no concrete red flag behind it must not raise the badge at
    all — only a footnote."""
    for cat, conf in [("financial_scam", 0.985),
                      ("political_propaganda", 0.88),
                      ("health_misinformation", 0.90)]:
        v = build_verdict(
            classification(category=cat, confidence=conf, flags=[]),
            account(), {}, "Sunset at Hunza valley yesterday.", ["caption"],
        )
        assert v["level"] == "clean", f"{cat} raised the badge with no flags"
        assert v["notes"], f"{cat} should leave an explanatory footnote"
        assert v["content"]["category_counted"] is False


def test_uncorroborated_category_is_not_listed_as_a_reason():
    v = build_verdict(
        classification(category="financial_scam", confidence=0.985, flags=[]),
        account(), {}, "Sunset at Hunza valley.", ["caption"],
    )
    assert not any("financial scam" in r.lower() for r in v["reasons"])


def test_headline_never_names_a_non_risk_category():
    """Flags fire while the model says `credible` — the real quackery case.
    The headline must describe the flags, not say 'Possible credible'."""
    v = build_verdict(
        classification(category="credible", confidence=0.995,
                       flags=[flag("health_claim", "high", "Unsupported health claims")]),
        account(), {}, "This one root CURES diabetes in 3 weeks", ["caption"],
    )
    assert "credible" not in v["headline"].lower()
    assert v["level"] in ("warning", "danger")


def test_credible_category_with_scam_flags_is_not_waved_through():
    """The classifier called real quackery 'credible' at 0.995. The red-flag
    layer is what catches those, so it must raise the badge on its own."""
    v = build_verdict(
        classification(category="credible", confidence=0.97,
                       flags=[flag(), flag("health_claim", "high", "Health claims")]),
        account(), {}, "Lose weight fast! DM me now", ["caption"],
    )
    assert v["level"] == "danger"          # two high-severity flags
    assert v["content"]["red_flag_count"] == 2


def test_flag_type_names_match_the_post_checker():
    """A typo in a flag name silently downgrades a real scam, so the names are
    asserted against the post checker's FLAG_SEVERITY table."""
    from analyzer import HIGH_FLAGS, MEDIUM_FLAGS, LOW_FLAGS
    known = {
        "financial_promise", "health_claim", "urgency", "engagement_bait",
        "off_platform_contact", "phone_number", "hashtag_stuffing", "shouting",
        "link_pushing",
        # contributed by the link and claim checkers
        "link_risk", "impossible_claim",
    }
    assert (HIGH_FLAGS | MEDIUM_FLAGS | LOW_FLAGS) <= known


def test_low_severity_flags_alone_stay_calm():
    """Link-in-bio and hashtags are ordinary creator behaviour."""
    v = build_verdict(
        classification(flags=[flag("link_pushing", "low", "External links"),
                              flag("hashtag_stuffing", "low", "Hashtag stuffing")]),
        account(), {}, "New post! link in bio #a #b #c", ["caption"],
    )
    assert v["level"] in ("clean", "caution")
    assert v["level"] != "warning"


def test_clean_text_and_real_account_is_clean():
    v = build_verdict(classification(), account(), {},
                      "Had a great day at the beach with friends.", ["caption"])
    assert v["level"] == "clean"
    assert v["not_checked"] == []


# --------------------------------------------------------------------------- #
# Honesty about missing evidence
# --------------------------------------------------------------------------- #
def test_empty_text_is_never_clean():
    """No text means the content check was vacuous. Reporting that as 'clean'
    would have the product vouching for something it never read."""
    v = build_verdict(classification(), account(), {}, "", [])
    assert v["level"] != "clean"
    assert any("no caption" in n.lower() for n in v["not_checked"])


def test_reel_without_speech_is_never_green():
    """Observed live: a reel showed a green "Nothing suspicious found" while its
    own small print admitted the audio was never transcribed. For a reel the
    speech *is* the content, so a reassuring verdict there is false comfort."""
    v = build_verdict(
        classification(), account(), {},
        "UNLIMITED BUDGET: WHICH CAR", ["on_screen_text"], is_reel=True,
    )
    assert v["level"] == "unknown"
    assert v["headline"] == "Spoken audio not checked yet"
    assert v["coverage"]["partial"] is True
    assert not any(r.startswith("No scam patterns") for r in v["reasons"])


def test_reel_with_speech_read_can_be_clean():
    v = build_verdict(
        classification(), account(),
        {"available": True, "is_reliable": True, "confidence": 0.9,
         "quality": "good", "char_count": 400, "language": "en"},
        "the full spoken transcript", ["caption", "speech"], is_reel=True,
    )
    assert v["level"] == "clean"
    assert v["coverage"]["partial"] is False


def test_unheard_reel_still_warns_when_flags_fired():
    """Only the reassuring direction is downgraded. Evidence already found stays
    — hearing the audio could only make it worse, never better."""
    v = build_verdict(
        classification(category="financial_scam", flags=[flag()]),
        account(), {}, "GUARANTEED PROFIT", ["caption"], is_reel=True,
    )
    assert v["level"] == "danger"
    assert v["coverage"]["partial"] is False


def test_photo_post_without_account_data_can_still_be_clean():
    """Instagram does not render follower counts in the feed, so requiring the
    account signal would turn every feed post grey and make the badge useless."""
    v = build_verdict(classification(), {"available": False, "error": "no profile data"},
                      {}, "A nice photo of my lunch", ["caption"], is_reel=False)
    assert v["level"] == "clean"


def test_classifier_down_is_reported_not_hidden():
    v = build_verdict(UNAVAILABLE, account(), {}, "some text", ["caption"])
    assert v["content"]["level"] == "unknown"
    assert any("content" in n.lower() for n in v["not_checked"])


def test_failed_transcription_is_listed_as_unchecked():
    v = build_verdict(
        classification(), account(),
        {"available": False, "error": "download blocked"},
        "caption only", ["caption"],
    )
    assert any("spoken audio" in n.lower() for n in v["not_checked"])


def test_unreliable_transcript_is_flagged_even_when_available():
    v = build_verdict(
        classification(), account(),
        {"available": True, "is_reliable": False, "confidence": 0.2,
         "quality": "poor", "char_count": 40, "language": "ur"},
        "some transcript", ["speech"],
    )
    assert any("unclear" in n.lower() for n in v["not_checked"])


# --------------------------------------------------------------------------- #
# Account signal
# --------------------------------------------------------------------------- #
def test_bot_account_raises_level_even_when_text_is_fine():
    v = build_verdict(classification(), account(band="fake", prob_fake=0.95),
                      {}, "Nice photo", ["caption"])
    assert v["level"] in ("warning", "caution")
    assert v["account"]["band"] == "fake"


def test_uncertain_account_is_caution_not_clean():
    v = build_verdict(classification(), account(band="uncertain", prob_fake=0.55),
                      {}, "Nice photo", ["caption"])
    assert v["level"] == "caution"


def test_low_margin_category_is_carried_in_the_evidence():
    """A coin-flip category is footnoted, not asserted — but the low_margin fact
    still has to reach the explainer so it can be honest about it."""
    v = build_verdict(
        classification(category="health_misinformation", confidence=0.41, low_margin=True),
        account(), {}, "detox tea cures everything", ["caption"],
    )
    cat = [e for e in v["evidence"] if e["kind"] == "category"]
    assert cat and cat[0]["low_margin"] is True
    assert v["notes"], "an uncorroborated category should footnote itself"


def test_verdict_carries_text_and_sources_for_the_explainer():
    v = build_verdict(classification(), account(), {}, "hello world", ["caption", "speech"])
    assert v["text_analyzed"] == "hello world"
    assert v["text_sources"] == ["caption", "speech"]
