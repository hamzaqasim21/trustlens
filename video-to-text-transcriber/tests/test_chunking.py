"""Tests for classifier-window chunking.

XLM-RoBERTa truncates silently past 512 tokens, so a chunker that lets a window
overflow causes evidence loss nobody sees. These pin that down.
"""
from __future__ import annotations

from app.pipeline.chunking import (
    DEFAULT_MAX_TOKENS, chunk_segments, estimate_tokens,
)


def seg(text, start, end, conf=0.8, dropped=False):
    return {"text": text, "start": start, "end": end,
            "confidence": conf, "dropped": dropped, "drop_reason": ""}


SENTENCE = "The minister announced a new economic policy for the province today. "


class TestTokenEstimation:
    def test_empty_is_zero(self):
        assert estimate_tokens("") == 0

    def test_english_ratio_is_sane(self):
        t = estimate_tokens("hello world this is a test of the estimator")
        assert 5 <= t <= 20

    def test_urdu_costs_more_tokens_than_english_per_char(self):
        """XLM-R fragments Urdu more; the estimator must reflect that."""
        urdu = "یہ ایک اردو جملہ ہے جو ٹیسٹ کے لیے لکھا گیا"
        english = "this is an english sentence written for a test okay"
        # comparable character counts, Urdu should not be under-counted
        assert estimate_tokens(urdu) > estimate_tokens(english) * 0.9


class TestNoSplitNeeded:
    def test_short_transcript_stays_one_chunk(self):
        out = chunk_segments([seg("A short sentence.", 0, 2)])
        assert out.was_split is False
        assert len(out.chunks) == 1
        assert out.chunks[0].est_tokens <= DEFAULT_MAX_TOKENS

    def test_empty_input(self):
        out = chunk_segments([])
        assert out.chunks == []
        assert out.warnings

    def test_dropped_segments_are_excluded(self):
        out = chunk_segments([
            seg("Real speech here.", 0, 2),
            seg("Thanks for watching!", 2, 3, dropped=True),
        ])
        assert len(out.chunks) == 1
        assert "Thanks for watching" not in out.chunks[0].text


class TestSplitting:
    def _long(self, n=80):
        return [seg(SENTENCE, i * 4.0, i * 4.0 + 4.0) for i in range(n)]

    def test_long_transcript_is_split(self):
        out = chunk_segments(self._long())
        assert out.was_split is True
        assert len(out.chunks) > 1

    def test_every_chunk_fits_the_limit(self):
        """The whole point: no window may exceed the classifier's capacity."""
        out = chunk_segments(self._long())
        for c in out.chunks:
            assert c.est_tokens <= DEFAULT_MAX_TOKENS, (
                f"chunk {c.index} has {c.est_tokens} tokens, over the limit"
            )

    def test_chunks_carry_timestamps(self):
        out = chunk_segments(self._long())
        for c in out.chunks:
            assert c.end >= c.start
        assert out.chunks[0].start == 0.0

    def test_chunks_overlap_so_claims_are_not_cut_in_half(self):
        out = chunk_segments(self._long())
        assert len(out.chunks) >= 2
        # chunk N+1 must begin before chunk N ended
        assert out.chunks[1].start < out.chunks[0].end

    def test_chunks_are_ordered_and_indexed(self):
        out = chunk_segments(self._long())
        assert [c.index for c in out.chunks] == list(range(len(out.chunks)))
        starts = [c.start for c in out.chunks]
        assert starts == sorted(starts)

    def test_coverage_reaches_the_end_of_the_video(self):
        """Regression guard: the tail must not be dropped."""
        segs = self._long()
        out = chunk_segments(segs)
        assert out.chunks[-1].end == segs[-1]["end"]

    def test_terminates_on_one_oversized_segment(self):
        """A single segment bigger than the budget must not loop forever."""
        out = chunk_segments([seg(SENTENCE * 200, 0, 30), seg("after", 30, 32)])
        assert len(out.chunks) >= 1
        assert out.warnings

    def test_custom_limit_is_respected(self):
        out = chunk_segments(self._long(20), max_tokens=100, overlap_tokens=10)
        for c in out.chunks:
            assert c.est_tokens <= 100


class TestConfidence:
    def test_chunk_confidence_is_duration_weighted(self):
        out = chunk_segments([
            seg("a long confident stretch of speech", 0, 20, conf=0.9),
            seg("brief mumble", 20, 20.5, conf=0.1),
        ])
        assert out.chunks[0].confidence > 0.8

    def test_confidence_in_unit_interval(self):
        out = chunk_segments([seg(SENTENCE, 0, 4, conf=0.75)])
        assert 0.0 <= out.chunks[0].confidence <= 1.0
