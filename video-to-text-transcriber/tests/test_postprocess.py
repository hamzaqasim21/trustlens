"""Tests for hallucination filtering and confidence scoring.

The filter is the difference between handing the classifier real speech and
handing it Whisper's invented YouTube-subtitle boilerplate. A false negative
here becomes a misinformation verdict on text nobody ever said.
"""
from __future__ import annotations

import math

from app.pipeline.postprocess import (
    clean_transcript, repetition_score, segment_confidence,
)


def seg(text, start=0.0, end=2.0, logprob=-0.3, nsp=0.05, cr=1.5):
    return {
        "start": start, "end": end, "text": text,
        "avg_logprob": logprob, "no_speech_prob": nsp, "compression_ratio": cr,
    }


class TestRepetitionScore:
    def test_normal_sentence_scores_zero(self):
        assert repetition_score(
            "the government announced a new policy for farmers across the province today"
        ) == 0.0

    def test_repeated_phrase_is_caught(self):
        text = "subscribe to my channel " * 8
        assert repetition_score(text) > 0.5

    def test_single_word_hammered_is_caught(self):
        assert repetition_score("hello hello hello hello hello hello hello") > 0.5

    def test_short_text_is_exempt(self):
        assert repetition_score("hi hi hi") == 0.0

    def test_empty_is_safe(self):
        assert repetition_score("") == 0.0


class TestSegmentConfidence:
    def test_clean_speech_scores_high(self):
        c = segment_confidence(avg_logprob=-0.2, no_speech_prob=0.02)
        assert c > 0.75

    def test_weak_logprob_scores_low(self):
        assert segment_confidence(avg_logprob=-2.0, no_speech_prob=0.1) < 0.2

    def test_high_no_speech_prob_crushes_confidence(self):
        """A segment the model thinks is silence cannot be highly confident."""
        assert segment_confidence(avg_logprob=-0.1, no_speech_prob=0.95) < 0.1

    def test_matches_exp_of_logprob(self):
        # The mapping should be the actual geometric-mean token probability.
        assert segment_confidence(-0.5, 0.0) == round(math.exp(-0.5), 4)

    def test_bounded_to_unit_interval(self):
        assert 0.0 <= segment_confidence(-99.0, 0.0) <= 1.0
        assert 0.0 <= segment_confidence(0.0, 0.0) <= 1.0


class TestHallucinationFiltering:
    def test_youtube_outro_boilerplate_is_dropped(self):
        out = clean_transcript([
            seg("The minister said prices will fall next month."),
            seg("Thanks for watching!", start=2, end=3),
            seg("Please subscribe", start=3, end=4),
        ])
        assert out.kept_count == 1
        assert out.dropped_count == 2
        assert "Thanks for watching" not in out.text

    def test_music_tags_are_dropped(self):
        out = clean_transcript([seg("[Music]"), seg("♪♪♪", start=2, end=4)])
        assert out.kept_count == 0
        assert out.quality == "unusable"

    def test_repetition_loop_is_dropped(self):
        out = clean_transcript([
            seg("This is a normal opening statement about the news today."),
            seg("buy now buy now buy now buy now buy now buy now buy now", start=2, end=9),
        ])
        assert out.kept_count == 1
        assert any("repetition" in s.drop_reason for s in out.segments if s.dropped)

    def test_silence_with_weak_logprob_is_dropped(self):
        out = clean_transcript([seg("mumble", logprob=-1.8, nsp=0.92)])
        assert out.kept_count == 0

    def test_duplicate_neighbours_are_dropped(self):
        line = "the same sentence repeated verbatim by the decoder"
        out = clean_transcript([seg(line), seg(line, start=2, end=4), seg(line, start=4, end=6)])
        assert out.kept_count == 1

    def test_genuine_speech_survives(self):
        out = clean_transcript([
            seg("Doctors have confirmed this remedy cures diabetes in two weeks.", 0, 5),
            seg("Pharmaceutical companies do not want you to know this.", 5, 9),
        ])
        assert out.kept_count == 2
        assert out.dropped_count == 0
        assert out.quality in ("good", "fair")
        assert out.confidence > 0.5

    def test_thanks_for_watching_inside_a_sentence_is_kept(self):
        """Only whole-segment matches are boilerplate; real usage must survive."""
        out = clean_transcript([
            seg("She said thanks for watching the demonstration and then left the stage.", 0, 6)
        ])
        assert out.kept_count == 1


class TestAggregation:
    def test_confidence_is_duration_weighted(self):
        """A long confident segment should outweigh a short shaky one."""
        out = clean_transcript([
            seg("a long and clearly articulated statement of fact", 0, 20, logprob=-0.15),
            seg("uh what", 20, 20.5, logprob=-1.2, nsp=0.3),
        ])
        assert out.confidence > 0.65

    def test_empty_input_is_handled(self):
        out = clean_transcript([])
        assert out.text == ""
        assert out.confidence == 0.0
        assert out.quality == "unusable"
        assert out.kept_count == 0

    def test_warns_when_most_segments_filtered(self):
        out = clean_transcript([
            seg("A real sentence that carries actual meaning here.", 0, 3),
            seg("Thanks for watching!", 3, 4),
            seg("[Music]", 4, 5),
            seg("♪", 5, 6),
        ])
        assert any("half" in w for w in out.warnings)

    def test_drop_reasons_are_reported(self):
        out = clean_transcript([seg("Thanks for watching!"), seg("[Music]", 2, 3)])
        assert out.stats["drop_reasons"]

    def test_speech_seconds_counts_only_kept(self):
        out = clean_transcript([
            seg("Real content here that should be kept in full.", 0, 10),
            seg("Thanks for watching!", 10, 20),
        ])
        assert 9.0 <= out.speech_seconds <= 11.0
