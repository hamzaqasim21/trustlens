"""Stage 5 - split a long transcript into classifier-sized windows.

Why this is not optional
------------------------
The Misinformation Classifier is XLM-RoBERTa, which has a hard 512-token input
limit. A three-minute reel transcribes to roughly 700-900 tokens in English and
noticeably more in Urdu, because XLM-R's SentencePiece vocabulary splits Urdu
into more pieces per word than English.

Hand that to the classifier unchunked and HuggingFace silently truncates at 512.
No error, no warning - the model just never sees the back half of the video. A
scam claim in the final thirty seconds would be invisible, and the verdict would
look perfectly confident while being based on partial evidence. That is the worst
possible failure mode for a system whose entire purpose is trustworthy verdicts.

So we chunk here, in the transcriber, where the timestamps and per-segment
confidences still exist to attach to each window.

Design choices
--------------
* Split on segment boundaries, never mid-sentence. Whisper's segments already
  align to natural pauses, so they are the right seams.
* Overlap consecutive windows. A claim straddling a boundary would otherwise be
  cut in half and lose its meaning in both windows.
* Carry timestamps and confidence per chunk, so a flagged chunk can be pointed
  at a specific moment in the video and weighted by how well it was heard.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

log = logging.getLogger(__name__)

# XLM-RoBERTa's limit is 512 including <s> and </s>. Leave headroom so a caller
# that prepends a prompt or a language tag does not tip over the edge.
DEFAULT_MAX_TOKENS = 480
DEFAULT_OVERLAP_TOKENS = 64

# Characters per token, measured against XLM-R's SentencePiece vocabulary.
# Urdu and other Arabic-script languages fragment more than Latin script does,
# so a single ratio would badly under-count Urdu and let chunks overflow.
_CHARS_PER_TOKEN = {
    "latin": 4.0,
    "arabic": 2.6,       # ur, ar, fa, ps, sd
    "devanagari": 2.8,   # hi, mr
}


@dataclass
class Chunk:
    index: int
    text: str
    start: float
    end: float
    confidence: float
    est_tokens: int
    segment_count: int
    is_overlap_continuation: bool = False

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class ChunkedTranscript:
    chunks: list[Chunk]
    total_est_tokens: int
    max_tokens: int
    was_split: bool
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "chunks": [asdict(c) for c in self.chunks],
            "chunk_count": len(self.chunks),
            "total_est_tokens": self.total_est_tokens,
            "max_tokens_per_chunk": self.max_tokens,
            "was_split": self.was_split,
            "warnings": self.warnings,
        }


def _script_of(text: str) -> str:
    from app.pipeline.language import profile_script

    return profile_script(text).dominant


def estimate_tokens(text: str, script: str | None = None) -> int:
    """Approximate XLM-R token count without loading the tokenizer.

    If `transformers` happens to be installed we use the real tokenizer, because
    an exact count is strictly better. Otherwise we fall back to a script-aware
    character ratio, which is close enough given we already keep 32 tokens of
    headroom.
    """
    if not text.strip():
        return 0

    exact = _exact_tokens(text)
    if exact is not None:
        return exact

    script = script or _script_of(text)
    ratio = _CHARS_PER_TOKEN.get(script, _CHARS_PER_TOKEN["latin"])
    return max(1, int(len(text) / ratio))


_tokenizer = None
_tokenizer_tried = False


def _exact_tokens(text: str) -> int | None:
    """Use the real XLM-R tokenizer when it is available locally."""
    global _tokenizer, _tokenizer_tried
    if _tokenizer_tried and _tokenizer is None:
        return None
    if _tokenizer is None:
        _tokenizer_tried = True
        try:
            from transformers import AutoTokenizer

            _tokenizer = AutoTokenizer.from_pretrained(
                "xlm-roberta-base", local_files_only=True
            )
        except Exception:
            _tokenizer = None
            return None
    try:
        return len(_tokenizer.encode(text, add_special_tokens=True))
    except Exception:
        return None


def chunk_segments(
    segments: list[dict],
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> ChunkedTranscript:
    """Pack kept segments into windows that fit the classifier.

    `segments` are the post-filter dicts from `postprocess.clean_transcript`,
    already stripped of hallucinations. Dropped segments are ignored - there is
    no point spending classifier budget on text we do not believe.
    """
    kept = [s for s in segments if not s.get("dropped") and (s.get("text") or "").strip()]
    if not kept:
        return ChunkedTranscript([], 0, max_tokens, False,
                                 ["No usable segments to chunk."])

    script = _script_of(" ".join(s["text"] for s in kept[:20]))
    total = estimate_tokens(" ".join(s["text"] for s in kept), script)

    # Fits whole - hand back one chunk and skip the packing entirely.
    if total <= max_tokens:
        c = Chunk(
            index=0,
            text=" ".join(s["text"] for s in kept).strip(),
            start=float(kept[0].get("start") or 0.0),
            end=float(kept[-1].get("end") or 0.0),
            confidence=_weighted_conf(kept),
            est_tokens=total,
            segment_count=len(kept),
        )
        return ChunkedTranscript([c], total, max_tokens, False)

    chunks: list[Chunk] = []
    warnings: list[str] = []
    i = 0
    while i < len(kept):
        window: list[dict] = []
        tokens = 0
        j = i
        while j < len(kept):
            t = estimate_tokens(kept[j]["text"], script)
            if window and tokens + t > max_tokens:
                break
            window.append(kept[j])
            tokens += t
            j += 1

        # A single segment can exceed the whole budget on its own - Whisper
        # occasionally emits one very long run with no pause. Packing it whole
        # would hand the classifier a window it silently truncates, which is the
        # exact failure this module exists to prevent. Split it on word
        # boundaries instead so every emitted window genuinely fits.
        if len(window) == 1 and tokens > max_tokens:
            for piece in _split_oversized(window[0], script, max_tokens):
                chunks.append(Chunk(
                    index=len(chunks),
                    text=piece["text"],
                    start=piece["start"],
                    end=piece["end"],
                    confidence=float(window[0].get("confidence") or 0.0),
                    est_tokens=piece["tokens"],
                    segment_count=1,
                    is_overlap_continuation=len(chunks) > 0,
                ))
            warnings.append(
                f"A single {tokens}-token segment at "
                f"{float(window[0].get('start') or 0):.0f}s was split on word "
                f"boundaries to fit the {max_tokens}-token classifier window."
            )
            i = j
            continue

        chunks.append(Chunk(
            index=len(chunks),
            text=" ".join(s["text"] for s in window).strip(),
            start=float(window[0].get("start") or 0.0),
            end=float(window[-1].get("end") or 0.0),
            confidence=_weighted_conf(window),
            est_tokens=tokens,
            segment_count=len(window),
            is_overlap_continuation=len(chunks) > 0,
        ))

        if j >= len(kept):
            break

        # Step back far enough to cover `overlap_tokens`, so a claim spanning the
        # seam appears intact in at least one window.
        back = 0
        acc = 0
        while back < len(window) - 1 and acc < overlap_tokens:
            acc += estimate_tokens(window[-(back + 1)]["text"], script)
            back += 1
        i = max(i + 1, j - back)

    return ChunkedTranscript(chunks, total, max_tokens, True, warnings)


def _split_oversized(segment: dict, script: str, max_tokens: int) -> list[dict]:
    """Break one over-long segment into word-boundary pieces that each fit.

    Timestamps are interpolated across the segment by word position. That is an
    approximation, but it keeps every chunk pointing at roughly the right moment
    in the video, which is what the Trust Score Engine needs to cite evidence.
    """
    words = (segment.get("text") or "").split()
    if not words:
        return []

    start = float(segment.get("start") or 0.0)
    end = float(segment.get("end") or 0.0)
    span = max(0.0, end - start)

    pieces: list[dict] = []
    current: list[str] = []
    first_word_idx = 0

    def flush(upto_idx: int) -> None:
        if not current:
            return
        text = " ".join(current)
        p_start = start + (span * first_word_idx / len(words)) if len(words) else start
        p_end = start + (span * upto_idx / len(words)) if len(words) else end
        pieces.append({
            "text": text,
            "start": round(p_start, 3),
            "end": round(min(p_end, end) if end else p_end, 3),
            "tokens": estimate_tokens(text, script),
        })

    for idx, w in enumerate(words):
        trial = current + [w]
        if current and estimate_tokens(" ".join(trial), script) > max_tokens:
            flush(idx)
            current = [w]
            first_word_idx = idx
        else:
            current = trial

    flush(len(words))
    return pieces


def _weighted_conf(segments: list[dict]) -> float:
    """Duration-weighted mean confidence over a window."""
    total_dur = sum(
        max(0.0, float(s.get("end") or 0) - float(s.get("start") or 0)) for s in segments
    )
    if total_dur <= 0:
        vals = [float(s.get("confidence") or 0) for s in segments]
        return round(sum(vals) / len(vals), 4) if vals else 0.0
    acc = sum(
        float(s.get("confidence") or 0)
        * max(0.0, float(s.get("end") or 0) - float(s.get("start") or 0))
        for s in segments
    )
    return round(acc / total_dur, 4)
