"""Language and script handling, with a Pakistani-content bias.

Why this module exists
----------------------
Urdu and Hindi are the same spoken language (Hindustani) written in two
different scripts. Whisper's training data contains far more Hindi than Urdu,
so when it hears Pakistani Urdu it very often:

  1. tags the language as `hi` instead of `ur`, and
  2. writes the transcript out in Devanagari instead of Urdu Arabic script.

Downstream that is a real problem: our misinformation classifier is fine-tuned
on Urdu Arabic script (UrduFake and friends), so a Devanagari transcript would
be tokenised into near-garbage.

We attack it at three points:
  * detection - probe several windows and vote, then apply an explicit
    ur-over-hi preference because our domain is Pakistani content;
  * decoding  - prime the decoder with an Urdu-script `initial_prompt`, which
    biases it toward emitting Urdu characters;
  * repair    - if Devanagari still comes out, transliterate it back.

Code-switching (Urdu sentences with English words dropped in) is extremely
common in Pakistani reels, so we measure it and report it rather than trying
to force a single language.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Script detection
# --------------------------------------------------------------------------- #
_ARABIC_RANGES = (
    (0x0600, 0x06FF),   # Arabic
    (0x0750, 0x077F),   # Arabic Supplement
    (0x08A0, 0x08FF),   # Arabic Extended-A
    (0xFB50, 0xFDFF),   # Presentation Forms-A
    (0xFE70, 0xFEFF),   # Presentation Forms-B
)
_DEVANAGARI_RANGES = ((0x0900, 0x097F), (0xA8E0, 0xA8FF))

# Letters Urdu has that plain Arabic does not - a strong "this is Urdu" tell.
_URDU_ONLY = set("ٹڈڑںےہھگچپژکی")

LANGUAGE_NAMES = {
    "ur": "Urdu", "en": "English", "hi": "Hindi", "pa": "Punjabi",
    "ps": "Pashto", "sd": "Sindhi", "ar": "Arabic", "fa": "Persian",
}


def _in_ranges(cp: int, ranges) -> bool:
    return any(lo <= cp <= hi for lo, hi in ranges)


@dataclass
class ScriptProfile:
    arabic: int = 0
    devanagari: int = 0
    latin: int = 0
    digits: int = 0
    other: int = 0
    urdu_markers: int = 0

    @property
    def letters(self) -> int:
        return self.arabic + self.devanagari + self.latin

    def ratio(self, which: str) -> float:
        total = self.letters
        return (getattr(self, which) / total) if total else 0.0

    @property
    def dominant(self) -> str:
        if not self.letters:
            return "none"
        return max(
            (("arabic", self.arabic), ("devanagari", self.devanagari), ("latin", self.latin)),
            key=lambda kv: kv[1],
        )[0]

    def as_dict(self) -> dict:
        return {
            "dominant": self.dominant,
            "arabic_ratio": round(self.ratio("arabic"), 4),
            "devanagari_ratio": round(self.ratio("devanagari"), 4),
            "latin_ratio": round(self.ratio("latin"), 4),
            "urdu_marker_count": self.urdu_markers,
            "letter_count": self.letters,
        }


def profile_script(text: str) -> ScriptProfile:
    p = ScriptProfile()
    for ch in text:
        cp = ord(ch)
        if ch.isdigit():
            p.digits += 1
        elif _in_ranges(cp, _ARABIC_RANGES):
            p.arabic += 1
            if ch in _URDU_ONLY:
                p.urdu_markers += 1
        elif _in_ranges(cp, _DEVANAGARI_RANGES):
            p.devanagari += 1
        elif ch.isalpha() and cp < 0x0250:
            p.latin += 1
        elif not ch.isspace():
            p.other += 1
    return p


def is_code_switched(text: str, min_minor_ratio: float = 0.08) -> bool:
    """True when a meaningful amount of both a native script and Latin appear."""
    p = profile_script(text)
    if p.letters < 12:
        return False
    native = max(p.ratio("arabic"), p.ratio("devanagari"))
    latin = p.ratio("latin")
    return native >= min_minor_ratio and latin >= min_minor_ratio


# --------------------------------------------------------------------------- #
# Decoder priming
# --------------------------------------------------------------------------- #
# A short, neutral Urdu-script sentence. Whisper conditions on this, which pulls
# its output distribution toward Urdu orthography instead of Devanagari.
URDU_PRIMER = "یہ ایک اردو ویڈیو ہے۔ اس میں گفتگو اردو زبان میں کی جا رہی ہے۔"
ENGLISH_PRIMER = ""


def initial_prompt_for(language: str | None) -> str | None:
    if language == "ur":
        return URDU_PRIMER
    return None


# --------------------------------------------------------------------------- #
# Language decision
# --------------------------------------------------------------------------- #
@dataclass
class LanguageDecision:
    language: str
    probability: float
    detected_raw: str                       # what Whisper actually said
    corrected: bool = False
    reason: str = ""
    candidates: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "language": self.language,
            "language_name": LANGUAGE_NAMES.get(self.language, self.language),
            "probability": round(self.probability, 4),
            "detected_raw": self.detected_raw,
            "corrected": self.corrected,
            "reason": self.reason,
            "candidates": {k: round(v, 4) for k, v in
                           sorted(self.candidates.items(), key=lambda kv: -kv[1])[:6]},
        }


def decide_language(
    candidates: dict[str, float],
    urdu_bias: bool = True,
    urdu_min_prob: float = 0.15,
    allowed: list[str] | None = None,
) -> LanguageDecision:
    """Turn raw per-language probabilities into a final call.

    The one opinionated rule: if Whisper says Hindi but Urdu is also plausible,
    take Urdu. TrustLens analyses Pakistani accounts, so `hi` on Hindustani
    speech is far more likely to be a script/training artefact than a genuine
    Hindi speaker.
    """
    if not candidates:
        return LanguageDecision("en", 0.0, "en", reason="no detection signal")

    ranked = sorted(candidates.items(), key=lambda kv: -kv[1])
    top, top_p = ranked[0]
    ur_p = candidates.get("ur", 0.0)

    decision = LanguageDecision(
        language=top, probability=top_p, detected_raw=top, candidates=candidates
    )

    if urdu_bias and top == "hi" and ur_p >= urdu_min_prob:
        decision.language = "ur"
        decision.probability = max(ur_p, top_p)
        decision.corrected = True
        decision.reason = (
            f"Whisper reported Hindi (p={top_p:.2f}) but Urdu was also plausible "
            f"(p={ur_p:.2f}). Hindustani speech is routinely mislabelled as Hindi; "
            f"TrustLens targets Pakistani content, so Urdu was selected."
        )
        return decision

    if allowed and decision.language not in allowed:
        decision.reason = (
            f"Detected {LANGUAGE_NAMES.get(top, top)} which is outside the configured "
            f"allow-list; transcribing anyway and flagging for review."
        )
    return decision


# --------------------------------------------------------------------------- #
# Devanagari -> Urdu repair
# --------------------------------------------------------------------------- #
# Fallback map used when `aksharamukha` is not installed. It is a consonant and
# vowel approximation, not a scholarly transliteration - good enough to keep the
# text tokenisable by an Urdu model, and we always flag when it has been used.
_DEVA_TO_URDU = {
    "अ": "ا", "आ": "آ", "इ": "ا", "ई": "ای", "उ": "ا", "ऊ": "او",
    "ए": "اے", "ऐ": "ای", "ओ": "او", "औ": "او",
    "क": "ک", "ख": "کھ", "ग": "گ", "घ": "گھ", "ङ": "ن",
    "च": "چ", "छ": "چھ", "ज": "ج", "झ": "جھ", "ञ": "ن",
    "ट": "ٹ", "ठ": "ٹھ", "ड": "ڈ", "ढ": "ڈھ", "ण": "ن",
    "त": "ت", "थ": "تھ", "द": "د", "ध": "دھ", "न": "ن",
    "प": "پ", "फ": "پھ", "ब": "ب", "भ": "بھ", "म": "م",
    "य": "ی", "र": "ر", "ल": "ل", "व": "و",
    "श": "ش", "ष": "ش", "स": "س", "ह": "ہ",
    "क़": "ق", "ख़": "خ", "ग़": "غ", "ज़": "ز", "ड़": "ڑ", "ढ़": "ڑھ",
    "फ़": "ف", "ऴ": "ل",
    "ा": "ا", "ि": "", "ी": "ی", "ु": "", "ू": "و",
    "े": "ے", "ै": "ے", "ो": "و", "ौ": "و",
    "ं": "ں", "ँ": "ں", "ः": "", "्": "", "़": "",
    "।": "۔", "॥": "۔", "०": "٠", "१": "١", "२": "٢", "३": "٣", "४": "٤",
    "५": "٥", "६": "٦", "७": "٧", "८": "٨", "९": "٩",
}


def _fallback_transliterate(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return "".join(_DEVA_TO_URDU.get(ch, ch) for ch in text)


def devanagari_to_urdu(text: str) -> tuple[str, str]:
    """Return (converted_text, method). Method is 'aksharamukha' | 'builtin' | 'none'."""
    if not text.strip():
        return text, "none"
    try:
        from aksharamukha import transliterate  # type: ignore

        out = transliterate.process("Devanagari", "Urdu", text)
        if out and out.strip():
            return out, "aksharamukha"
    except Exception as exc:
        log.debug("aksharamukha unavailable or failed (%s); using builtin map.", exc)
    return _fallback_transliterate(text), "builtin"


def repair_script(text: str, target_language: str) -> tuple[str, dict]:
    """If we asked for Urdu and got Devanagari, convert it back.

    Returns the (possibly rewritten) text plus a report describing what happened,
    so the API response can stay honest about it.
    """
    report = {"applied": False, "method": "none", "before": None}
    if target_language != "ur" or not text.strip():
        return text, report

    p = profile_script(text)
    if p.ratio("devanagari") < 0.30:
        return text, report

    converted, method = devanagari_to_urdu(text)
    report.update({
        "applied": True,
        "method": method,
        "before": text[:400],
        "devanagari_ratio": round(p.ratio("devanagari"), 4),
        "note": (
            "Whisper emitted Hindi (Devanagari) script for Urdu speech. Text was "
            "transliterated to Urdu Arabic script so the misinformation classifier "
            "receives the script it was trained on."
        ),
    })
    return converted, report


# --------------------------------------------------------------------------- #
# Cleanup
# --------------------------------------------------------------------------- #
_WS = re.compile(r"[ \t ]+")
_NL = re.compile(r"\n{3,}")


def normalise_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("​", "").replace("﻿", "")
    text = _WS.sub(" ", text)
    text = _NL.sub("\n\n", text)
    return text.strip()
