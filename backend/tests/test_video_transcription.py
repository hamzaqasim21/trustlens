"""
Module 12 - Video-to-Text Transcriber, website side.

No network and no speech model: the RapidAPI calls, Whisper and the
misinformation model are all replaced by fakes, so these tests check the
pipeline's own logic - which reels are heard, what counts toward the score,
what is reported when something can't be heard, and the Urdu handling.
"""
import pytest

import data_ingestion as di
import scan_service
import urdu_language as ul

# --------------------------------------------------------------------------- #
# Reading Instagram's data
# --------------------------------------------------------------------------- #
MPD = """<?xml version="1.0"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011"><Period>
 <AdaptationSet contentType="video" mimeType="video/mp4">
  <Representation bandwidth="900000"><BaseURL>https://x.cdninstagram.com/video.mp4</BaseURL></Representation>
 </AdaptationSet>
 <AdaptationSet contentType="audio" mimeType="audio/mp4">
  <Representation bandwidth="128000"><BaseURL>https://x.cdninstagram.com/audio_high.mp4</BaseURL></Representation>
  <Representation bandwidth="48000"><BaseURL>https://x.cdninstagram.com/audio_low.mp4</BaseURL></Representation>
 </AdaptationSet>
</Period></MPD>"""


def test_lowest_bitrate_audio_track_is_chosen():
    assert di.audio_url_from_manifest(MPD) == "https://x.cdninstagram.com/audio_low.mp4"


def test_no_or_broken_manifest_gives_no_audio_link():
    assert di.audio_url_from_manifest(None) == ""
    assert di.audio_url_from_manifest("<MPD><not closed") == ""
    video_only = MPD.split("<AdaptationSet contentType=\"audio\"")[0] + "</Period></MPD>"
    assert di.audio_url_from_manifest(video_only) == ""


def test_photos_have_no_reel_media_and_videos_do():
    assert di.reel_media({"code": "P1", "media_type": 1}) is None
    m = di.reel_media({"code": "R1", "video_versions": [{"url": "https://v"}],
                       "video_dash_manifest": MPD, "has_audio": True, "taken_at": 5})
    assert m == {"code": "R1", "audio_url": "https://x.cdninstagram.com/audio_low.mp4",
                 "video_url": "https://v", "has_audio": True, "taken_at": 5, "product_type": ""}


# --------------------------------------------------------------------------- #
# Urdu handling
# --------------------------------------------------------------------------- #
def test_hindi_label_is_written_out_as_urdu():
    d = ul.decide_language({"hi": 0.87, "ur": 0.02, "en": 0.05})
    assert d["language"] == "ur" and d["corrected"] and d["detected_raw"] == "hi"
    assert d["probability"] == pytest.approx(0.89)


def test_other_languages_are_left_alone():
    d = ul.decide_language({"en": 0.98, "hi": 0.01})
    assert d["language"] == "en" and not d["corrected"]
    assert ul.decide_language({})["language"] is None


def test_devanagari_is_converted_to_urdu_script_only_for_urdu():
    text, converted = ul.repair_script("नमस्ते दोस्तों", "ur")
    assert converted
    ratios = ul.script_ratios(text)
    assert ratios["devanagari"] == 0 and ratios["arabic"] > 0.9
    assert ul.repair_script("नमस्ते", "hi") == ("नमस्ते", False)
    assert ul.repair_script("یہ اردو ہے", "ur") == ("یہ اردو ہے", False)


def test_nukta_letters_convert_to_their_own_urdu_letter():
    text, _ = ul.repair_script("ज़िंदगी ज़िंदगी", "ur")
    assert text.startswith("ز")


def test_urdu_primer_is_only_used_for_urdu():
    assert ul.initial_prompt_for("ur") and ul.initial_prompt_for("en") is None


# --------------------------------------------------------------------------- #
# What the user typed
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("typed,expected", [
    ("cristiano", ("username", "cristiano")),
    ("@duckybhai ", ("username", "duckybhai")),
    ("https://www.instagram.com/nasa/", ("username", "nasa")),
    ("instagram.com/nasa?igsh=abc", ("username", "nasa")),
    ("https://www.instagram.com/reel/DdwFxNQIJDx/?igsh=MTc4", ("post", "DdwFxNQIJDx")),
    ("https://www.instagram.com/reels/DdwFxNQIJDx/", ("post", "DdwFxNQIJDx")),
    ("https://instagram.com/p/C6GrdLrIHNL", ("post", "C6GrdLrIHNL")),
    ("https://www.instagram.com/duckybhai/reel/DdwFxNQIJDx/", ("post", "DdwFxNQIJDx")),
    ("", (None, None)),
])
def test_scan_box_accepts_usernames_profile_links_and_post_links(typed, expected):
    assert scan_service.parse_scan_input(typed) == expected


def test_other_instagram_links_are_refused_clearly():
    with pytest.raises(scan_service.ScanFailed) as e:
        scan_service.parse_scan_input("https://www.instagram.com/explore/")
    assert e.value.kind == "invalid"


# --------------------------------------------------------------------------- #
# Which reels are heard
# --------------------------------------------------------------------------- #
def reel(code, t, sound=True):
    return {"code": code, "audio_url": f"https://a/{code}", "video_url": f"https://v/{code}",
            "has_audio": sound, "taken_at": t}


def test_newest_reels_with_sound_are_picked():
    picked = scan_service._pick_reels([reel("oldreel", 1), reel("silent", 9, False), reel("new", 8),
                                       reel("mid", 5), reel("older", 2)])
    assert [r["code"] for r in picked] == ["new", "mid", "older"]


def test_submitted_reel_always_comes_first_and_is_not_repeated():
    picked = scan_service._pick_reels([reel("a", 3), reel("b", 2), reel("c", 1)],
                                      focus=dict(reel("b", 2), is_video=True))
    assert [r["code"] for r in picked] == ["b", "a", "c"]
    assert picked[0]["submitted"] and not picked[1]["submitted"]


def test_time_limit_reports_unheard_reels_instead_of_hiding_them(monkeypatch):
    monkeypatch.setattr(scan_service, "REEL_TIME_BUDGET", -1)
    heard = scan_service._listen_to_reels([reel("a", 1)], transcribe=lambda *a, **k: 1 / 0)
    assert heard[0]["available"] is False and "time limit" in heard[0]["error"]


# --------------------------------------------------------------------------- #
# The whole scan, with fakes
# --------------------------------------------------------------------------- #
PROFILE = {"username": "some.creator", "full_name": "Some Creator", "followers": 50000,
           "following": 300, "posts": 120, "has_profile_pic": 1, "bio_length": 20,
           "has_external_url": 0, "is_private": 0, "is_verified": False,
           "biography": "Food and travel"}


def transcript(text, reliable=True, no_speech=False, lang="en"):
    return {"available": True, "text": text, "no_speech": no_speech, "is_reliable": reliable,
            "quality": "none" if no_speech else ("good" if reliable else "rough"),
            "language": lang, "language_name": ul.language_name(lang)}


def fake_classify(text):
    scam = "guaranteed" in text.lower()
    category = "financial_scam" if scam else "credible"
    scores = {"credible": 0.02 if scam else 0.97, "financial_scam": 0.98 if scam else 0.01,
              "health_misinformation": 0.0, "political_propaganda": 0.01,
              "sensational_clickbait": 0.0, "urdu_misinformation": 0.01}
    return {"status": "success", "misinformation_flag": scam, "primary_category": category,
            "confidence": scores[category], "category_scores": scores,
            "risk_score": 98 if scam else 3}


@pytest.fixture
def pipeline(monkeypatch):
    """Fakes for the network and the models. Returns a dict the test fills:
    reels (reel_media), transcripts (code -> transcript), calls (what was heard)."""
    state = {"reels": [], "transcripts": {}, "calls": [], "media": None}

    def engagement(username):
        return {"avg_likes": 2000, "avg_comments": 60, "posts_analyzed": 12,
                "post_codes": ["c1"], "post_captions": ["Dinner in Lahore tonight"],
                "posts": [], "comments_off": False, "reel_media": list(state["reels"])}

    def transcribe(code, audio_url, video_url, careful=False):
        state["calls"].append((code, careful))
        return dict(state["transcripts"][code])

    monkeypatch.setattr(scan_service, "fetch_instagram_profile", lambda u: dict(PROFILE))
    monkeypatch.setattr(scan_service, "fetch_engagement_data", engagement)
    monkeypatch.setattr(scan_service, "fetch_post_comments", lambda code: [])
    monkeypatch.setattr(scan_service, "classify_text", fake_classify)
    monkeypatch.setattr(scan_service, "calculate_credential_confidence",
                        lambda *a, **k: {"confidence_score": None, "claims_found": []})
    monkeypatch.setattr(scan_service, "fetch_media_data", lambda code: dict(state["media"]))
    monkeypatch.setattr(scan_service.video_transcriber, "transcribe_reel", transcribe)
    return state


def test_clear_speech_is_checked_and_can_decide_the_score(pipeline):
    pipeline["reels"] = [reel("r1", 2), reel("r2", 1)]
    pipeline["transcripts"] = {
        "r1": transcript("Guaranteed 300% returns, send money on WhatsApp today"),
        "r2": transcript("Here is how we cooked this biryani"),
    }
    result = scan_service.analyze_username("some.creator")

    speech = [s for s in result["misinformation_sources"] if s["source"] == "reel_speech"]
    assert [s["reel_code"] for s in speech] == ["r1", "r2"]
    # the scam is in the speech only, and it decides the misinformation module
    assert result["misinformation_analysis"]["source"] == "reel_speech"
    assert result["misinformation_analysis"]["primary_category"] == "financial_scam"
    vt = result["video_transcription"]
    assert vt["status"] == "done" and vt["reels_listened"] == 2 and vt["reels_counted"] == 2
    assert vt["items"][0]["counted"] and vt["items"][0]["assessment"]["misinformation_flag"]
    # signed links are used during the scan but never stored
    assert "reel_media" not in result["engagement_data"]
    assert "audio_url" not in str(vt)


def test_unclear_speech_and_silence_are_shown_but_never_scored(pipeline):
    pipeline["reels"] = [reel("music", 2), reel("quiet", 1)]
    pipeline["transcripts"] = {
        "music": transcript("Guaranteed 300% returns", reliable=False),
        "quiet": transcript("", no_speech=True),
    }
    result = scan_service.analyze_username("some.creator")
    assert not [s for s in result["misinformation_sources"] if s["source"] == "reel_speech"]
    assert result["misinformation_analysis"]["primary_category"] == "credible"
    items = {i["code"]: i for i in result["video_transcription"]["items"]}
    assert items["music"]["text"] and not items["music"]["counted"]
    assert "unclear" in items["music"]["not_counted_reason"]
    assert items["quiet"]["not_counted_reason"] == "no speech in this reel"


def test_a_reel_that_could_not_be_heard_is_reported_not_assumed_clean(pipeline):
    pipeline["reels"] = [reel("r1", 1)]
    pipeline["transcripts"] = {"r1": {"available": False, "error": "couldn't get this reel's audio"}}
    vt = scan_service.analyze_username("some.creator")["video_transcription"]
    assert vt["status"] == "unavailable" and vt["reels_listened"] == 0
    assert vt["items"][0]["not_counted_reason"] == "couldn't get this reel's audio"


def test_account_without_reels_says_so(pipeline):
    vt = scan_service.analyze_username("some.creator")["video_transcription"]
    assert vt["status"] == "no_reels" and vt["items"] == [] and "No reels" in vt["message"]


def test_reel_link_scans_the_poster_and_listens_carefully_to_that_reel(pipeline):
    pipeline["reels"] = [reel("r1", 5), reel("r2", 4), reel("r3", 3)]
    pipeline["transcripts"] = {c: transcript("Hello everyone") for c in ("oldreel", "r1", "r2")}
    pipeline["media"] = {"code": "oldreel", "username": "some.creator", "is_video": True,
                         "has_audio": True, "audio_url": "https://a/oldreel", "video_url": "https://v/oldreel",
                         "caption": "Guaranteed 300% returns in 7 days, DM me",
                         "like_count": 10, "comment_count": 2}

    class DB:
        pass
    monkeypatch_save = scan_service.save_scan
    scan_service.save_scan = lambda db, uid, result, source="web": None
    try:
        result = scan_service.run_scan(DB(), 1, "https://www.instagram.com/reel/oldreel/?igsh=x")
    finally:
        scan_service.save_scan = monkeypatch_save

    # submitted reel first, with the careful model; then the 2 newest others
    assert pipeline["calls"] == [("oldreel", True), ("r1", False), ("r2", False)]
    assert result["submitted_post"]["code"] == "oldreel"
    assert result["video_transcription"]["items"][0]["submitted"]
    # its caption is older than the recent posts, but still checked
    caps = [s for s in result["misinformation_sources"] if s.get("submitted")]
    assert caps and caps[0]["primary_category"] == "financial_scam"


def test_photo_link_still_scans_the_poster(pipeline):
    pipeline["media"] = {"code": "picpost", "username": "some.creator", "is_video": False,
                         "has_audio": False, "caption": "Sunset", "audio_url": "", "video_url": ""}
    scan_service.save_scan, keep = (lambda *a, **k: None), scan_service.save_scan
    try:
        result = scan_service.run_scan(object(), 1, "https://www.instagram.com/p/picpost/")
    finally:
        scan_service.save_scan = keep
    assert result["submitted_post"]["is_video"] is False
    assert "photo post" in result["video_transcription"]["message"]


# --------------------------------------------------------------------------- #
# Urdu speech: a warning label only counts with a red flag behind it
# --------------------------------------------------------------------------- #
def urdu_model(text):
    """Behaves like the real classifier did on ordinary Urdu reels: 99% Urdu misinformation."""
    scores = {"credible": 0.005, "financial_scam": 0.0, "health_misinformation": 0.0,
              "political_propaganda": 0.0, "sensational_clickbait": 0.005,
              "urdu_misinformation": 0.99}
    return {"status": "success", "misinformation_flag": True, "primary_category": "urdu_misinformation",
            "confidence": 0.99, "category_scores": scores, "risk_score": 99}


def test_unbacked_urdu_label_on_speech_is_shown_but_not_scored(pipeline, monkeypatch):
    monkeypatch.setattr(scan_service, "classify_text",
                        lambda t: urdu_model(t) if t.startswith("ہم") else fake_classify(t))
    pipeline["reels"] = [reel("ur1", 1)]
    pipeline["transcripts"] = {"ur1": transcript("ہم لوگ ڈرائیو کرنے والے ہیں", lang="ur")}
    result = scan_service.analyze_username("some.creator")
    item = result["video_transcription"]["items"][0]
    assert not item["counted"] and "Urdu speech" in item["not_counted_reason"]
    assert item["assessment"]["primary_category"] == "urdu_misinformation"   # still shown
    assert result["misinformation_analysis"]["source"] != "reel_speech"


def test_urdu_speech_with_a_red_flag_is_scored(pipeline, monkeypatch):
    monkeypatch.setattr(scan_service, "classify_text", urdu_model)
    pipeline["reels"] = [reel("ur2", 1)]
    pipeline["transcripts"] = {"ur2": transcript(
        "ہم guaranteed 50% monthly returns دیتے ہیں، abhi invest karein", lang="ur")}
    result = scan_service.analyze_username("some.creator")
    item = result["video_transcription"]["items"][0]
    assert item["counted"] and item["assessment"]["red_flags"]
    assert result["misinformation_analysis"]["source"] == "reel_speech"


# --------------------------------------------------------------------------- #
# Reel links when Instagram's post lookup is down
# --------------------------------------------------------------------------- #
def _no_save(monkeypatch):
    monkeypatch.setattr(scan_service, "save_scan", lambda *a, **k: None)


def test_link_naming_the_account_still_scans_it_when_post_lookup_fails(pipeline, monkeypatch):
    _no_save(monkeypatch)

    def down(code):
        raise Exception('Instagram\'s data service didn\'t return this post ("Try again later").')
    monkeypatch.setattr(scan_service, "fetch_media_data", down)
    pipeline["reels"] = [reel("recent1", 2), reel("r2", 1)]
    pipeline["transcripts"] = {c: transcript("Hello") for c in ("recent1", "r2")}
    result = scan_service.run_scan(object(), 1, "https://www.instagram.com/some.creator/reel/recent1/")
    assert result["username"] == "some.creator"
    assert pipeline["calls"][0] == ("recent1", True)           # still heard first, carefully
    assert result["video_transcription"]["items"][0]["submitted"]


def test_older_post_with_lookup_down_is_explained(pipeline, monkeypatch):
    _no_save(monkeypatch)
    monkeypatch.setattr(scan_service, "fetch_media_data", lambda c: 1 / 0)
    result = scan_service.run_scan(object(), 1, "https://www.instagram.com/some.creator/p/oldpost1/")
    assert "isn't among this account's 12 most recent posts" in result["video_transcription"]["message"]
    assert result["submitted_post"]["is_video"] is None


def test_plain_reel_link_with_lookup_down_gives_a_clear_error(pipeline, monkeypatch):
    def down(code):
        raise Exception("Instagram's data service didn't return this post.")
    monkeypatch.setattr(scan_service, "fetch_media_data", down)
    with pytest.raises(scan_service.ScanFailed) as e:
        scan_service.run_scan(object(), 1, "https://www.instagram.com/reel/abcde12/")
    assert e.value.kind == "network" and "username" in str(e.value)


def test_scan_never_waits_past_the_reel_time_limit(pipeline, monkeypatch):
    """A reel stuck downloading must not hold the whole scan (found in a
    browser test: two scans at once, one reel failing, over five minutes)."""
    import time as _time
    monkeypatch.setattr(scan_service, "REEL_TIME_BUDGET", 0.6)
    pipeline["reels"] = [reel("fast", 3), reel("stuck", 2), reel("never", 1)]

    def transcribe(code, a, v, careful=False):
        if code == "stuck":
            _time.sleep(3)
        return transcript("Hello everyone")
    monkeypatch.setattr(scan_service.video_transcriber, "transcribe_reel", transcribe)

    started = _time.monotonic()
    result = scan_service.analyze_username("some.creator")
    assert _time.monotonic() - started < 2.5
    items = {i["code"]: i for i in result["video_transcription"]["items"]}
    assert items["fast"]["available"] and items["fast"]["counted"]
    assert items["stuck"]["available"] is False and "time limit" in items["stuck"]["error"]
    assert "time limit" in items["never"]["error"]
    assert [i["code"] for i in result["video_transcription"]["items"]] == ["fast", "stuck", "never"]


def test_speech_in_untrained_languages_is_shown_but_not_scored(pipeline):
    pipeline["reels"] = [reel("es1", 2), reel("en1", 1)]
    pipeline["transcripts"] = {
        "es1": transcript("Ganancias garantizadas del 300%, guaranteed returns", lang="es"),
        "en1": transcript("Here is how we cooked this biryani"),
    }
    result = scan_service.analyze_username("some.creator")
    items = {i["code"]: i for i in result["video_transcription"]["items"]}
    assert not items["es1"]["counted"] and "Spanish" in items["es1"]["not_counted_reason"]
    assert items["es1"]["text"]                           # still shown
    assert "assessment" not in items["es1"]               # no untrusted label displayed
    assert items["en1"]["counted"]
    assert result["misinformation_analysis"]["primary_category"] == "credible"
