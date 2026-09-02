"""Tests for the language / script layer.

These cover the Urdu-vs-Hindi handling, which is the part of this module most
likely to break silently: if it regresses, the pipeline still returns a
confident-looking transcript, just in the wrong script, and the misinformation
classifier quietly degrades. So it gets pinned down here.
"""
from __future__ import annotations

import pytest

from app.pipeline.language import (
    decide_language, is_code_switched, normalise_text, profile_script,
    repair_script, initial_prompt_for,
)

URDU = "یہ ایک اردو جملہ ہے جو ٹیسٹ کے لیے لکھا گیا ہے"
HINDI = "यह एक हिंदी वाक्य है जो टेस्ट के लिए लिखा गया है"
ENGLISH = "This is an English sentence written for testing"


class TestScriptProfiling:
    def test_detects_arabic_script(self):
        p = profile_script(URDU)
        assert p.dominant == "arabic"
        assert p.ratio("arabic") > 0.9
        assert p.urdu_markers > 0        # Urdu-only letters present

    def test_detects_devanagari(self):
        p = profile_script(HINDI)
        assert p.dominant == "devanagari"
        assert p.ratio("devanagari") > 0.9

    def test_detects_latin(self):
        p = profile_script(ENGLISH)
        assert p.dominant == "latin"

    def test_empty_text_is_safe(self):
        p = profile_script("")
        assert p.dominant == "none"
        assert p.ratio("arabic") == 0.0


class TestCodeSwitching:
    def test_flags_urdu_english_mix(self):
        # Very common in Pakistani reels.
        assert is_code_switched("یہ بہت important بات ہے اور سب کو pata ہونی چاہیے")

    def test_pure_urdu_is_not_code_switched(self):
        assert not is_code_switched(URDU)

    def test_pure_english_is_not_code_switched(self):
        assert not is_code_switched(ENGLISH)

    def test_short_text_is_not_flagged(self):
        assert not is_code_switched("ok ٹھیک")


class TestUrduBias:
    def test_hindi_with_plausible_urdu_becomes_urdu(self):
        """The core rule: Hindustani speech mislabelled as Hindi is corrected."""
        d = decide_language({"hi": 0.62, "ur": 0.31, "en": 0.05}, urdu_bias=True)
        assert d.language == "ur"
        assert d.corrected is True
        assert d.detected_raw == "hi"
        assert "Hindi" in d.reason

    def test_hindi_without_urdu_signal_stays_hindi(self):
        """Genuine Hindi must not be hijacked."""
        d = decide_language({"hi": 0.95, "ur": 0.01, "en": 0.02}, urdu_bias=True)
        assert d.language == "hi"
        assert d.corrected is False

    def test_bias_can_be_disabled(self):
        d = decide_language({"hi": 0.62, "ur": 0.31}, urdu_bias=False)
        assert d.language == "hi"
        assert d.corrected is False

    def test_threshold_is_respected(self):
        d = decide_language({"hi": 0.80, "ur": 0.10}, urdu_bias=True, urdu_min_prob=0.15)
        assert d.language == "hi"

    def test_english_is_untouched(self):
        d = decide_language({"en": 0.99, "cy": 0.01}, urdu_bias=True)
        assert d.language == "en"
        assert d.corrected is False

    def test_empty_candidates_defaults_safely(self):
        d = decide_language({}, urdu_bias=True)
        assert d.language == "en"
        assert d.probability == 0.0

    def test_out_of_allowlist_is_flagged_not_dropped(self):
        d = decide_language({"ja": 0.9}, urdu_bias=True, allowed=["ur", "en"])
        assert d.language == "ja"          # still transcribed
        assert "allow-list" in d.reason


class TestScriptRepair:
    def test_devanagari_for_urdu_is_converted(self):
        out, report = repair_script(HINDI, "ur")
        assert report["applied"] is True
        assert report["method"] in ("aksharamukha", "builtin")
        assert profile_script(out).ratio("devanagari") < 0.3

    def test_urdu_text_is_left_alone(self):
        out, report = repair_script(URDU, "ur")
        assert report["applied"] is False
        assert out == URDU

    def test_hindi_target_is_left_alone(self):
        out, report = repair_script(HINDI, "hi")
        assert report["applied"] is False
        assert out == HINDI

    def test_english_is_left_alone(self):
        out, report = repair_script(ENGLISH, "en")
        assert report["applied"] is False

    def test_empty_is_safe(self):
        out, report = repair_script("", "ur")
        assert report["applied"] is False


class TestPrompting:
    def test_urdu_gets_a_primer(self):
        p = initial_prompt_for("ur")
        assert p and profile_script(p).dominant == "arabic"

    def test_other_languages_get_none(self):
        assert initial_prompt_for("en") is None
        assert initial_prompt_for(None) is None


class TestNormalise:
    @pytest.mark.parametrize("raw,expected", [
        ("  hello   world  ", "hello world"),
        ("a\n\n\n\n\nb", "a\n\nb"),
        ("", ""),
    ])
    def test_whitespace(self, raw, expected):
        assert normalise_text(raw) == expected

    def test_strips_zero_width_characters(self):
        assert "​" not in normalise_text("test​text")
