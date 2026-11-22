"""
Urdu handling for reel transcription (Module 12, Video-to-Text Transcriber).

Ported from Ali Ahmad's first transcriber (archive/video_to_text_transcriber_old/
app/pipeline/language.py), keeping its three ideas and dropping the parts this
project doesn't use.

The problem it solves
---------------------
Urdu and Hindi are the same spoken language (Hindustani) written in two
different scripts. Whisper saw far more Hindi than Urdu in training, so when it
hears Pakistani Urdu it very often
  1. labels the language "hi" instead of "ur", and
  2. writes the words in Devanagari (Hindi script) instead of Urdu script.
Our misinformation classifier was trained on Urdu *script* (UrduFake), so a
Devanagari transcript would be close to unreadable for it.

What is done about it
---------------------
  * decide  - if Whisper says Hindi but Urdu is also plausible, take Urdu
              (TrustLens is aimed at Pakistani accounts);
  * prime   - start the decoder with a short Urdu-script sentence, which pulls
              its output toward Urdu letters;
  * repair  - if Devanagari still comes out, convert it letter by letter to
              Urdu script, and say so in the result.

This is rule-based text handling, not machine learning.
"""
from __future__ import annotations

import re
import unicodedata

LANGUAGE_NAMES = {
    "ur": "Urdu", "en": "English", "hi": "Hindi", "pa": "Punjabi",
    "ps": "Pashto", "sd": "Sindhi", "ar": "Arabic", "fa": "Persian",
    "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese",
    "tr": "Turkish", "id": "Indonesian", "it": "Italian", "ru": "Russian",
}

# Ali's version switched Hindi to Urdu only when Urdu also scored >= 15%.
# Measured on real Pakistani reels (Ducky Bhai, 2026-10-21): Whisper said Hindi
# at 87% with Urdu far below 15%, so the switch never happened and the
# transcript came out in Hindi script. Spoken Hindi and Urdu are the same
# language and our classifier only reads Urdu script, so Hindi is now always
# transcribed as Urdu (and the result says so).
URDU_MIN_PROB = 0.0

# A short, neutral Urdu sentence ("This is an Urdu video. The conversation in
# it is in Urdu."). Whisper conditions on it, which biases it toward Urdu script.
URDU_PRIMER = "یہ ایک اردو ویڈیو ہے۔ اس میں گفتگو اردو زبان میں کی جا رہی ہے۔"

_ARABIC_RANGES = ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF),
                  (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))
_DEVANAGARI_RANGES = ((0x0900, 0x097F), (0xA8E0, 0xA8FF))


def language_name(code: str | None) -> str:
    return LANGUAGE_NAMES.get(code or "", code or "Unknown")


def _in(cp: int, ranges) -> bool:
    return any(lo <= cp <= hi for lo, hi in ranges)


def script_ratios(text: str) -> dict:
    """Share of letters that are Urdu/Arabic script, Devanagari, or Latin."""
    arabic = deva = latin = 0
    for ch in text or "":
        cp = ord(ch)
        if _in(cp, _ARABIC_RANGES):
            arabic += 1
        elif _in(cp, _DEVANAGARI_RANGES):
            deva += 1
        elif ch.isalpha() and cp < 0x0250:
            latin += 1
    total = arabic + deva + latin
    if not total:
        return {"arabic": 0.0, "devanagari": 0.0, "latin": 0.0}
    return {"arabic": arabic / total, "devanagari": deva / total, "latin": latin / total}


def decide_language(candidates: dict[str, float]) -> dict:
    """Turn Whisper's per-language probabilities into the language to use.

    Returns {"language", "probability", "detected_raw", "corrected", "reason"}.
    """
    if not candidates:
        return {"language": None, "probability": 0.0, "detected_raw": None,
                "corrected": False, "reason": "no language signal"}
    top, top_p = max(candidates.items(), key=lambda kv: kv[1])
    ur_p = candidates.get("ur", 0.0)
    if top == "hi" and ur_p >= URDU_MIN_PROB:
        # The language confidence kept is Hindi + Urdu together: Whisper was
        # sure it heard Hindustani, only unsure which name to give it.
        return {
            "language": "ur", "probability": min(1.0, top_p + ur_p), "detected_raw": "hi",
            "corrected": True,
            "reason": ("Whisper labelled this Hindi. Spoken Hindi and Urdu are the same "
                       "language and Pakistani Urdu is routinely labelled Hindi, so it was "
                       "written out in Urdu script, which the misinformation model reads."),
        }
    return {"language": top, "probability": top_p, "detected_raw": top,
            "corrected": False, "reason": ""}


def initial_prompt_for(language: str | None) -> str | None:
    return URDU_PRIMER if language == "ur" else None


# Letter-by-letter Devanagari -> Urdu map (an approximation, not a scholarly
# transliteration: enough to keep the text readable by an Urdu-trained model).
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


def repair_script(text: str, language: str | None) -> tuple[str, bool]:
    """If Urdu was asked for and Devanagari came out anyway, convert it.
    Returns (text, converted?)."""
    if language != "ur" or not (text or "").strip():
        return text, False
    if script_ratios(text)["devanagari"] < 0.30:
        return text, False
    text = unicodedata.normalize("NFC", text)
    # Nukta letters (क़ etc.) are base letter + nukta mark after NFC; map
    # those pairs first, or the base letter alone would be used.
    for nukta, urdu in (("क़", "ق"), ("ख़", "خ"), ("ग़", "غ"), ("ज़", "ز"),
                        ("ड़", "ڑ"), ("ढ़", "ڑھ"), ("फ़", "ف")):
        text = text.replace(unicodedata.normalize("NFD", nukta), urdu).replace(nukta, urdu)
    return "".join(_DEVA_TO_URDU.get(ch, ch) for ch in text), True


_WS = re.compile(r"[ \t ]+")


def clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").replace("​", "").replace("﻿", "")
    return _WS.sub(" ", text).strip()
