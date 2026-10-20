"""
Tests for the rule-based red-flag detector.

Two halves, and the second matters more:

1. Scam text fires the right flags.
2. **Ordinary creator captions fire nothing.** A false positive escalates a
   badge on an innocent post, which is the failure a user actually notices
   and loses trust over. Missing a subtle scam is the cheaper error, because
   the category model is still watching in parallel.
"""
from __future__ import annotations

from analyzer import HIGH_FLAGS, LOW_FLAGS, MEDIUM_FLAGS
from red_flags import FLAG_SEVERITY, detect_red_flags, flag_pressure


def types_in(text: str) -> set[str]:
    return {f["type"] for f in detect_red_flags(text)}


# --------------------------------------------------------------------------- #
# The contract with analyzer.py
# --------------------------------------------------------------------------- #
def test_flag_names_match_the_analyzer_exactly():
    """A typo here silently downgrades a real scam instead of failing loudly,
    which is exactly the bug analyzer.py warns about in its own comments."""
    assert set(FLAG_SEVERITY) == (HIGH_FLAGS | MEDIUM_FLAGS | LOW_FLAGS)


def test_severities_agree_with_the_analyzer_buckets():
    for flag, severity in FLAG_SEVERITY.items():
        expected = ("high" if flag in HIGH_FLAGS
                    else "medium" if flag in MEDIUM_FLAGS else "low")
        assert severity == expected, f"{flag} is {severity}, analyzer expects {expected}"


def test_every_flag_carries_the_keys_the_analyzer_reads():
    flags = detect_red_flags(
        "GUARANTEED 300% RETURNS!! act now, only 3 spots left. DM me on whatsapp "
        "+92 300 1234567 https://bit.ly/x #a #b #c #d #e #f #g #h #i"
    )
    assert flags
    for f in flags:
        assert {"type", "title", "severity", "detail", "match_count"} <= set(f)


# --------------------------------------------------------------------------- #
# Scam text fires the right flags
# --------------------------------------------------------------------------- #
def test_guaranteed_returns_is_a_financial_promise():
    assert "financial_promise" in types_in("Guaranteed profit every single week.")
    assert "financial_promise" in types_in("Get 80% monthly returns on your deposit")


def test_named_disease_cure_is_a_health_claim():
    assert "health_claim" in types_in("This one root cures diabetes in a week")
    assert "health_claim" in types_in("Doctors hate this simple trick")


def test_absurd_arithmetic_is_an_impossible_claim():
    assert "impossible_claim" in types_in("500% guaranteed on every trade")
    assert "impossible_claim" in types_in("Lose 30 kg in 10 days with this tea")
    assert "impossible_claim" in types_in("Earn $5000 per day with zero experience")


def test_shortened_and_throwaway_links_are_link_risk():
    assert "link_risk" in types_in("Sign up here https://bit.ly/3xYz")
    assert "link_risk" in types_in("Join now http://freemoney.tk/offer")
    assert "link_risk" in types_in("Register at http://192.168.10.5/signup")


def test_pressure_tactics_are_medium():
    assert "urgency" in types_in("Act now, this offer expires tonight")
    assert "engagement_bait" in types_in('Comment "INFO" to get the link')
    assert "phone_number" in types_in("Reach me at +92 300 1234567")


def test_ordinary_promotion_is_only_low_severity():
    flags = detect_red_flags("New video is up, link in bio. DM me for collabs.")
    assert types_in("New video is up, link in bio. DM me for collabs.") == {
        "link_pushing", "off_platform_contact"
    }
    assert all(f["severity"] == "low" for f in flags)


def test_hashtag_stuffing_counts_rather_than_matches():
    caption = "sunset " + " ".join(f"#tag{i}" for i in range(12))
    assert "hashtag_stuffing" in types_in(caption)


def test_shouting_needs_sustained_capitals_not_one_word():
    assert "shouting" in types_in("BUY THIS RIGHT NOW BEFORE IT DISAPPEARS FOREVER")
    # A single emphasised word in a normal sentence is not shouting.
    assert "shouting" not in types_in("This was genuinely the BEST trip of my life")


# --------------------------------------------------------------------------- #
# The half that matters more: innocent captions stay clean
# --------------------------------------------------------------------------- #
INNOCENT = [
    "Morning coffee and a good book. Happy Sunday everyone.",
    "Behind the scenes from yesterday's shoot with the team.",
    "Three years at this company today. Grateful for every one of them.",
    "Recipe: two eggs, a cup of flour, and 30 minutes in the oven at 180C.",
    "Our AI research team published a new paper on model evaluation.",
    "Training for the marathon. 12 km this morning, legs are destroyed.",
    "The UK trip was unreal. Already planning the next one.",
    "New album out now on every streaming platform.",
]


def test_innocent_captions_raise_no_high_or_medium_flags():
    for caption in INNOCENT:
        flags = detect_red_flags(caption)
        serious = [f for f in flags if f["severity"] in ("high", "medium")]
        assert not serious, f"false positive on {caption!r}: {serious}"


def test_health_talk_without_a_disease_claim_is_not_flagged():
    """Ordinary wellness content must not be treated as a medical claim."""
    assert "health_claim" not in types_in(
        "Drinking more water genuinely improved my skin and energy levels."
    )


def test_normal_price_and_year_numbers_are_not_phone_numbers():
    assert "phone_number" not in types_in("Tickets are 2500 rupees, doors open 2026.")


def test_empty_text_returns_nothing():
    assert detect_red_flags("") == []
    assert detect_red_flags("   ") == []


# --------------------------------------------------------------------------- #
# Pressure scoring
# --------------------------------------------------------------------------- #
def test_flag_pressure_weights_high_above_low():
    high_only = detect_red_flags("Guaranteed profit every week")
    low_only = detect_red_flags("Link in bio")
    assert flag_pressure(high_only) > flag_pressure(low_only)


def test_flag_pressure_of_nothing_is_zero():
    assert flag_pressure([]) == 0


def test_fake_prize_messages_are_flagged():
    assert "prize_scam" in types_in(
        "Congratulations! You have won a free iPhone, text WIN to 80082 to claim your prize now")
    assert "prize_scam" in types_in("You've been selected to win $1000 cash")
    assert "prize_scam" in types_in("Pay a small fee to release your reward")
    assert "prize_scam" in types_in("Lottery winner announced, is it you?")


def test_ordinary_giveaways_are_not_prize_scams():
    for text in [
        "GIVEAWAY! Tag 2 friends to win this dress",
        "Congrats @sara_k, you won our giveaway! Check your DMs",
        "Follow and share to enter, winner announced Friday",
        "You have won my heart with this recipe",
        "Text me when you get home",
    ]:
        assert "prize_scam" not in types_in(text), text
