"""Stage 4 - clean the raw Whisper output and score how much to trust it.

Whisper has two well-documented failure modes that matter a lot for short
social-media clips, and both produce *confident-looking* text that is entirely
fabricated:

  1. Silence / music hallucination. Given a stretch with no speech, Whisper
     emits whatever most often followed silence in its training data - which was
     YouTube subtitles. So it writes "Thanks for watching!", "Subtitles by the
     Amara.org community", "Please subscribe", or the Arabic equivalent.

  2. Repetition loops. The decoder gets stuck emitting the same phrase over and
     over until the segment ends.

Feeding either into a misinformation classifier would be worse than feeding it
nothing, because the classifier has no way to know the text is invented. So we
filter, and we attach a calibrated confidence to everything that survives.

That confidence is not decoration - the scope document commits to showing a
confidence indicator with every verdict, and the Trust Score Engine is meant to
down-weight low-confidence evidence rather than treat all transcripts as equal.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field

from app.pipeline.language import is_code_switched, normalise_text, profile_script

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Known hallucination phrases
# --------------------------------------------------------------------------- #
# These are artefacts of Whisper being trained on scraped subtitle tracks.
# Matched case-insensitively against the *whole* stripped segment, so a genuine
# "thanks for watching" inside a longer sentence is not touched.
_HALLUCINATION_PHRASES = {
    # English - YouTube outro boilerplate
    "thanks for watching", "thank you for watching", "thanks for watching!",
    "thank you for watching!", "thanks for watching this video",
    "please subscribe", "subscribe to my channel", "like and subscribe",
    "don't forget to subscribe", "see you in the next video",
    "subtitles by the amara.org community", "amara.org",
    "transcription by castingwords", "subtitles by", "captions by",
    "www.mooji.org", "for more information visit", "bye bye", "bye!",
    "you", "thank you", "thank you.", "okay", "the end",
    # Bracketed sound tags
    "[music]", "[applause]", "[laughter]", "[silence]", "[inaudible]",
    "(music)", "(applause)", "(upbeat music)", "♪", "♪♪", "♪♪♪",
    # Arabic / Urdu subtitle boilerplate
    "شكرا للمشاهدة", "ترجمة نانسي قنقر", "اشترك في القناة", "شكرا لكم على المشاهدة",
    "دیکھنے کا شکریہ", "سبسکرائب کریں",
    # Hindi
    "देखने के लिए धन्यवाद", "सब्सक्राइब करें",
}

_MUSIC_ONLY = re.compile(r"^[\s♪♫\[\]\(\)\-–—.…*~]*$")


def _is_boilerplate(text: str) -> bool:
    t = text.strip().lower().strip(" .!?,-–—\"'“”")
    if not t:
        return True
    if _MUSIC_ONLY.match(text):
        return True
    return t in _HALLUCINATION_PHRASES


# --------------------------------------------------------------------------- #
# Repetition detection
# --------------------------------------------------------------------------- #
def repetition_score(text: str) -> float:
    """0.0 = no repetition, 1.0 = fully degenerate.

    Looks at word-level n-grams. A healthy sentence reuses very few 4-grams;
    a stuck decoder reuses almost nothing but.
    """
    words = re.findall(r"\w+", text.lower(), flags=re.UNICODE)
    if len(words) < 4:
        return 0.0

    worst = 0.0

    # Single word hammered over and over. Checked before the n-gram pass because
    # a short segment ("hello hello hello hello hello") is already degenerate at
    # a length the n-gram window would skip entirely.
    wc = Counter(words)
    top_word, top_wc = wc.most_common(1)[0]
    if top_wc >= 4 and len(top_word) > 2 and top_wc / len(words) >= 0.6:
        worst = max(worst, min(1.0, top_wc / len(words)))

    if len(words) < 8:
        return round(worst, 4)
    for n in (3, 4, 5):
        if len(words) < n * 2:
            continue
        grams = [tuple(words[i:i + n]) for i in range(len(words) - n + 1)]
        if not grams:
            continue
        counts = Counter(grams)
        top_gram, top_count = counts.most_common(1)[0]
        if top_count >= 3:
            worst = max(worst, min(1.0, (top_count * n) / len(words)))

    # Also catch a single word hammered over and over.
    wc = Counter(words)
    top_word, top_wc = wc.most_common(1)[0]
    if top_wc >= 5 and len(top_word) > 2:
        worst = max(worst, min(1.0, top_wc / len(words)))

    return round(worst, 4)


def _consecutive_duplicates(texts: list[str], window: int = 4) -> set[int]:
    """Indices of segments that just repeat a recent neighbour verbatim."""
    flagged: set[int] = set()
    for i, t in enumerate(texts):
        key = re.sub(r"\W+", "", t.lower())
        if len(key) < 6:
            continue
        for j in range(max(0, i - window), i):
            if re.sub(r"\W+", "", texts[j].lower()) == key:
                flagged.add(i)
                break
    return flagged


# --------------------------------------------------------------------------- #
# Confidence
# --------------------------------------------------------------------------- #
def segment_confidence(avg_logprob: float, no_speech_prob: float) -> float:
    """Map Whisper's internal scores onto a 0-1 confidence.

    `avg_logprob` is the mean log-probability per token, so exp() of it is the
    geometric-mean token probability - a genuinely meaningful quantity rather
    than an arbitrary curve. In practice clean speech lands around -0.15 to
    -0.45 (=> 0.86 to 0.64) and junk falls below -1.0 (=> under 0.37).

    We then scale by (1 - no_speech_prob), because a segment the model itself
    believes is silence should not score highly no matter how confident the
    token distribution looked.
    """
    try:
        base = math.exp(max(min(avg_logprob, 0.0), -5.0))
    except (OverflowError, ValueError):
        base = 0.0
    speech = 1.0 - max(0.0, min(1.0, no_speech_prob))
    return round(max(0.0, min(1.0, base * speech)), 4)


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class Segment:
    index: int
    start: float
    end: float
    text: str
    confidence: float
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0
    compression_ratio: float = 0.0
    repetition: float = 0.0
    dropped: bool = False
    drop_reason: str = ""
    code_switched: bool = False
    words: list[dict] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class CleanTranscript:
    text: str
    segments: list[Segment]
    confidence: float
    quality: str                       # good | fair | poor | unusable
    kept_count: int
    dropped_count: int
    speech_seconds: float
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def as_dict(self, include_words: bool = False) -> dict:
        segs = []
        for s in self.segments:
            d = asdict(s)
            if not include_words:
                d.pop("words", None)
            segs.append(d)
        return {
            "text": self.text,
            "segments": segs,
            "confidence": self.confidence,
            "quality": self.quality,
            "kept_segments": self.kept_count,
            "dropped_segments": self.dropped_count,
            "speech_seconds": round(self.speech_seconds, 2),
            "warnings": self.warnings,
            "stats": self.stats,
        }


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
def clean_transcript(
    raw_segments: list[dict],
    *,
    no_speech_threshold: float = 0.6,
    logprob_threshold: float = -1.0,
    compression_threshold: float = 2.4,
    repetition_threshold: float = 0.55,
    min_confidence: float = 0.10,
) -> CleanTranscript:
    """Filter hallucinations out of raw Whisper segments and score the rest."""
    segments: list[Segment] = []
    texts = [normalise_text(s.get("text", "")) for s in raw_segments]
    dup_idx = _consecutive_duplicates(texts)

    for i, raw in enumerate(raw_segments):
        text = texts[i]
        avg_lp = float(raw.get("avg_logprob") or 0.0)
        nsp = float(raw.get("no_speech_prob") or 0.0)
        cr = float(raw.get("compression_ratio") or 0.0)
        rep = repetition_score(text)
        conf = segment_confidence(avg_lp, nsp)

        seg = Segment(
            index=i,
            start=round(float(raw.get("start") or 0.0), 3),
            end=round(float(raw.get("end") or 0.0), 3),
            text=text,
            confidence=conf,
            avg_logprob=round(avg_lp, 4),
            no_speech_prob=round(nsp, 4),
            compression_ratio=round(cr, 4),
            repetition=rep,
            code_switched=is_code_switched(text),
            words=raw.get("words") or [],
        )

        reason = ""
        if not text.strip():
            reason = "empty"
        elif _is_boilerplate(text):
            reason = "known-hallucination-phrase"
        elif nsp > no_speech_threshold and avg_lp < logprob_threshold:
            reason = f"no-speech (p={nsp:.2f}) with weak logprob ({avg_lp:.2f})"
        elif rep >= repetition_threshold:
            reason = f"repetition-loop (score={rep:.2f})"
        elif cr > compression_threshold and rep > 0.25:
            reason = f"low-entropy repetitive text (compression={cr:.2f})"
        elif i in dup_idx:
            reason = "duplicate of a neighbouring segment"
        elif conf < min_confidence:
            reason = f"confidence below floor ({conf:.2f})"

        if reason:
            seg.dropped = True
            seg.drop_reason = reason

        segments.append(seg)

    kept = [s for s in segments if not s.dropped]
    dropped = [s for s in segments if s.dropped]

    text = normalise_text(" ".join(s.text for s in kept))
    speech_seconds = sum(s.duration for s in kept)

    # Duration-weighted confidence: a 12-second confident segment should count
    # for more than a 0.4-second uncertain one.
    if kept and speech_seconds > 0:
        overall = sum(s.confidence * s.duration for s in kept) / speech_seconds
    elif kept:
        overall = sum(s.confidence for s in kept) / len(kept)
    else:
        overall = 0.0
    overall = round(overall, 4)

    warnings: list[str] = []
    if dropped:
        warnings.append(
            f"{len(dropped)} of {len(segments)} segments were filtered as likely "
            f"hallucination or silence."
        )
    if segments and len(dropped) / len(segments) > 0.5:
        warnings.append(
            "Over half the audio produced no reliable speech - the clip is probably "
            "mostly music or noise."
        )
    if kept and sum(s.code_switched for s in kept) / len(kept) > 0.3:
        warnings.append(
            "Heavy Urdu-English code-switching detected; this is normal for Pakistani "
            "content but can reduce per-word accuracy."
        )
    if not text.strip():
        warnings.append("No usable speech was recovered from the audio track.")

    quality = _grade(overall, text, len(kept))
    if quality in ("poor", "unusable"):
        warnings.append(
            "Transcript quality is low. Treat any downstream misinformation verdict "
            "as provisional, and prefer the OCR / caption evidence if available."
        )

    prof = profile_script(text)
    stats = {
        "script": prof.as_dict(),
        "mean_no_speech_prob": round(
            sum(s.no_speech_prob for s in segments) / len(segments), 4
        ) if segments else 0.0,
        "max_repetition": max((s.repetition for s in segments), default=0.0),
        "char_count": len(text),
        "word_count": len(re.findall(r"\w+", text, flags=re.UNICODE)),
        "drop_reasons": dict(Counter(s.drop_reason for s in dropped)),
    }

    return CleanTranscript(
        text=text,
        segments=segments,
        confidence=overall,
        quality=quality,
        kept_count=len(kept),
        dropped_count=len(dropped),
        speech_seconds=speech_seconds,
        warnings=warnings,
        stats=stats,
    )


def _grade(confidence: float, text: str, kept: int) -> str:
    words = len(re.findall(r"\w+", text, flags=re.UNICODE))
    if kept == 0 or words < 3:
        return "unusable"
    if confidence >= 0.70 and words >= 15:
        return "good"
    if confidence >= 0.50:
        return "fair"
    if confidence >= 0.30:
        return "poor"
    return "unusable"
