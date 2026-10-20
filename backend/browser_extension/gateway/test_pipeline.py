"""
Tests for the extension's RapidAPI + listening pipeline (gateway/main.py).

No network: RapidAPI, the two model services and Whisper are replaced with
fakes, so these run in under a second and never spend quota. What they pin
down is the wiring — which data wins, what counts as "checked", and that a
missing account is never scored.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))

import analyzer  # noqa: E402
import clients  # noqa: E402
import instagram_data  # noqa: E402
import main  # noqa: E402
import reel_audio  # noqa: E402

REEL = "https://www.instagram.com/reels/ABCdef123/"

MEDIA = {
    "available": True, "code": "ABCdef123", "caption": "Morning routine for a calm day",
    "username": "real_creator", "full_name": "Real Creator", "is_verified": True,
    "is_private": False, "is_video": True, "has_audio": True,
    "video_url": "https://cdn.example/video.mp4", "like_count": 1200, "comment_count": 40,
}
ENGAGEMENT = {"available": True, "avg_likes": 6000, "avg_comments": 150, "posts_analyzed": 12}
MODEL_CLEAN = {"status": "success", "primary_category": "credible", "confidence": 0.9,
               "risk_score": 5, "category_scores": {"credible": 0.95, "financial_scam": 0.01,
                                                    "political_propaganda": 0.02,
                                                    "health_misinformation": 0.01,
                                                    "sensational_clickbait": 0.01}}
PROFILE = {
    "available": True, "username": "real_creator", "full_name": "Real Creator",
    "followers": 250000, "following": 300, "posts": 900, "has_profile_pic": True,
    "bio_length": 40, "biography": "Coach. Podcast every Monday.", "has_external_url": True,
    "is_private": False, "is_verified": True,
}


@pytest.fixture
def fakes(monkeypatch):
    calls = {"profile": [], "predict": [], "listen": 0, "classify": []}

    async def get_media(code):
        calls.setdefault("rapidapi_media", []).append(code)
        return dict(MEDIA, code=code)

    async def get_profile(username):
        calls["profile"].append(username)
        if username == "ghost_account":
            return {"available": False, "error": "user does not exist on Instagram"}
        return dict(PROFILE)

    async def predict_account(features):
        calls["predict"].append(features)
        return {"available": True, "prob_fake": 0.02, "band": "real", "confidence": 0.96,
                "verdict": "Low Risk — Likely Genuine"}

    async def classify_text(text):
        calls["classify"].append(text)
        return {"available": True, "category": "credible", "category_label": "Credible",
                "confidence": 0.9, "post_risk_score": 5, "red_flags": [],
                "model_result": dict(MODEL_CLEAN)}

    heard: dict = {}

    def transcribe(code, url, progress, on_screen=True):
        calls["listen"] += 1
        calls.setdefault("urls", []).append(url)
        progress(50, "Listening…")
        heard[code] = {"available": True, "text": "Today I share my simple morning routine.",
                       "no_speech": False, "language": "en", "confidence": 0.99,
                       "quality": "good", "is_reliable": True, "char_count": 40}
        return heard[code]

    monkeypatch.setattr(instagram_data, "get_media", get_media)
    async def get_engagement(username):
        calls.setdefault("engagement", []).append(username)
        return dict(ENGAGEMENT)

    monkeypatch.setattr(instagram_data, "get_profile", get_profile)
    monkeypatch.setattr(instagram_data, "get_engagement", get_engagement)
    monkeypatch.setattr(clients, "predict_account", predict_account)
    monkeypatch.setattr(clients, "classify_text", classify_text)
    monkeypatch.setattr(reel_audio, "transcribe", transcribe)
    monkeypatch.setattr(reel_audio, "cached", lambda code: heard.get(code))
    return calls


@pytest.fixture
def api():
    return TestClient(main.app)


def test_shortcode_is_read_from_every_url_shape():
    for url in ["https://www.instagram.com/reel/ABCdef123/",
                "https://www.instagram.com/reels/ABCdef123/?igsh=x",
                "https://www.instagram.com/p/ABCdef123/"]:
        assert instagram_data.shortcode_from(url) == "ABCdef123"
    assert instagram_data.shortcode_from("https://www.instagram.com/reels/") is None


def test_real_caption_and_poster_come_from_instagram_not_the_page(api, fakes):
    v = api.post("/analyze", json={"page_url": REEL, "caption": "stale page text",
                                   "username": "viewer_own_account", "is_reel": True}).json()
    assert v["post"]["author"] == "real_creator"
    assert v["post"]["caption_source"] == "instagram"
    assert "Morning routine" in v["text_analyzed"]
    assert "stale page text" not in v["text_analyzed"]
    # the page's wrong guess must not be the account that gets scored
    assert fakes["predict"][-1]["username"] == "real_creator"


def test_poster_is_scored_with_the_same_inputs_the_website_uses(api, fakes):
    api.post("/analyze", json={"page_url": REEL, "is_reel": True})
    f = fakes["predict"][-1]
    assert f["followers_count"] == 250000 and f["follows_count"] == 300
    assert f["posts_count"] == 900 and f["full_name"] == "Real Creator"
    assert f["has_external_url"] == 1 and f["profile_pic"] == 1


def test_reel_is_not_green_until_its_audio_is_checked(api, fakes):
    v = api.post("/analyze", json={"page_url": REEL, "is_reel": True}).json()
    assert v["level"] == "unknown" and v["score"] is None
    assert v["coverage"]["can_listen"] is True
    assert fakes["listen"] == 0

    v = api.post("/analyze", json={"page_url": REEL, "is_reel": True, "transcribe": True}).json()
    assert fakes["listen"] == 1
    assert "speech" in v["text_sources"]
    assert v["level"] == "clean" and v["score"] >= 82
    assert v["coverage"]["speech_read"] is True and v["coverage"]["can_listen"] is False


def test_music_only_reel_counts_as_checked(api, fakes, monkeypatch):
    monkeypatch.setattr(reel_audio, "transcribe", lambda c, u, p, o=True: {
        "available": True, "text": "", "no_speech": True, "quality": "none",
        "is_reliable": False})
    v = api.post("/analyze", json={"page_url": REEL, "is_reel": True, "transcribe": True}).json()
    assert v["coverage"]["speech_read"] is True
    assert v["level"] == "clean"
    assert any("no speech" in r for r in v["reasons"])
    assert not any("unclear" in n for n in v["not_checked"])


def test_account_that_does_not_exist_is_never_scored(api, fakes, monkeypatch):
    async def ghost_media(code):
        return dict(MEDIA, username="ghost_account")
    monkeypatch.setattr(instagram_data, "get_media", ghost_media)
    v = api.post("/analyze", json={"page_url": REEL, "is_reel": True}).json()
    assert fakes["predict"] == []
    assert v["account"]["prob_fake"] is None
    assert any("does not exist" in n for n in v["not_checked"])


def test_scam_caption_still_caught_when_instagram_has_no_record(api, fakes, monkeypatch):
    async def no_media(code):
        return {"available": False, "error": "not found"}

    async def scam_classify(text):
        return {"available": True, "category": "financial_scam",
                "category_label": "Financial Scam", "confidence": 0.99,
                "post_risk_score": 100,
                "red_flags": [{"type": "financial_promise", "severity": "high"},
                              {"type": "impossible_claim", "severity": "high"}],
                "model_result": {"status": "success", "primary_category": "financial_scam",
                                 "confidence": 0.99, "risk_score": 99,
                                 "category_scores": {"financial_scam": 0.99, "credible": 0.01}}}
    monkeypatch.setattr(instagram_data, "get_media", no_media)
    monkeypatch.setattr(clients, "classify_text", scam_classify)
    v = api.post("/analyze", json={"page_url": "https://www.instagram.com/p/NOPE12345/",
                                   "caption": "GUARANTEED 300% profit", "is_reel": False}).json()
    assert v["level"] == "danger" and v["score"] < 40
    assert v["score_label"] == "Content only"      # account unknown: says so
    assert v["post"]["caption_source"] == "page"


def test_profile_page_stats_are_used_without_spending_a_request(api, fakes):
    acct = {"username": "someone", "followers_count": 10, "follows_count": 5000,
            "posts_count": 1, "profile_pic": 0, "description_length": 0}
    api.post("/analyze", json={"page_url": "https://www.instagram.com/someone/",
                               "caption": "hello there friends", "account": acct})
    assert fakes["profile"] == []
    assert fakes["predict"][-1]["followers_count"] == 10


def test_missing_profile_is_refused_not_zero_filled(monkeypatch):
    sys.path.insert(0, str(instagram_data.BACKEND_DIR))
    import data_ingestion

    class Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"error": "Invalid or missing username or user does not exist on Instagram"}

    monkeypatch.setattr(data_ingestion.requests, "post", lambda *a, **k: Resp())
    # Its own error type, so the website can say "check the spelling" rather
    # than "try again" — see ScanPage.jsx.
    with pytest.raises(data_ingestion.ProfileNotFoundError, match="no public Instagram account"):
        data_ingestion.fetch_instagram_profile("ghost_account")


def test_analyzer_no_speech_is_a_finding_not_a_gap():
    v = analyzer.build_verdict(
        {"available": True, "category": "credible", "red_flags": []},
        {"available": False, "error": "x"},
        {"available": True, "text": "", "no_speech": True},
        "a caption", ["caption"], is_reel=True)
    assert v["coverage"]["speech_read"] is True
    assert v["coverage"]["partial"] is False


def test_listening_starts_in_the_first_call_and_is_not_repeated(api, fakes):
    v = api.post("/analyze", json={"page_url": REEL, "is_reel": True, "listen": True}).json()
    assert v["coverage"]["listening"] is True
    assert v["level"] == "unknown"            # not called safe before the audio is in
    v = api.post("/analyze", json={"page_url": REEL, "is_reel": True, "transcribe": True}).json()
    assert v["coverage"]["speech_read"] is True and v["level"] == "clean"
    assert fakes["listen"] == 1               # the second call reused the first call's job


def test_progress_reports_listening_first_then_the_current_step(api):
    main._stages["https://x/reel/A1b2C3d4/"] = "Checking @someone's account…"
    assert api.get("/progress", params={"page_url": "https://x/reel/A1b2C3d4/"}).json()["stage"] \
        == "Checking @someone's account…"
    clients.set_progress("https://x/reel/A1b2C3d4/", state="running", percent=40, stage="Listening…")
    assert api.get("/progress", params={"page_url": "https://x/reel/A1b2C3d4/"}).json()["percent"] == 40
    clients.clear_progress("https://x/reel/A1b2C3d4/")
    main._stages.clear()


PAGE_ITEM = {"code": "ABCdef123", "caption": "Caption straight from the page's data",
             "username": "page_creator", "full_name": "Page Creator",
             "video_url": "https://scontent-ams2-1.cdninstagram.com/o1/v/reel.mp4",
             "has_audio": True, "like_count": 7, "comment_count": 1}


def test_page_data_is_used_instead_of_waiting_for_rapidapi(api, fakes, monkeypatch):
    instagram_data._cache.clear()
    monkeypatch.undo()   # use the real cache-first get_media for this test
    calls = {"rapidapi": 0}

    def rapid(code):
        calls["rapidapi"] += 1
        raise AssertionError("RapidAPI should not be called when the page already had the data")
    monkeypatch.setattr(instagram_data, "fetch_media_data", rapid)
    monkeypatch.setattr(instagram_data, "configured", lambda: True)

    async def get_profile(u):
        return {"available": False, "error": "skipped in test"}
    monkeypatch.setattr(instagram_data, "get_profile", get_profile)
    monkeypatch.setattr(instagram_data, "get_engagement", get_profile)

    async def classify_text(text):
        return {"available": True, "category": "credible", "red_flags": []}
    monkeypatch.setattr(clients, "classify_text", classify_text)

    v = api.post("/analyze", json={"page_url": REEL, "is_reel": True, "media": PAGE_ITEM}).json()
    assert calls["rapidapi"] == 0
    assert v["post"]["author"] == "page_creator"
    assert v["post"]["data_source"] == "instagram_page"
    assert "straight from the page" in v["text_analyzed"]
    instagram_data._cache.clear()


def test_page_data_cannot_point_the_server_at_another_website():
    bad = dict(PAGE_ITEM, video_url="http://127.0.0.1:8000/admin")
    assert instagram_data.clean_page_media(bad)["video_url"] == ""
    bad = dict(PAGE_ITEM, video_url="https://cdninstagram.com.evil.example/x.mp4")
    assert instagram_data.clean_page_media(bad)["video_url"] == ""
    assert instagram_data.clean_page_media(dict(PAGE_ITEM, code="../../etc")) is None
    assert instagram_data.clean_page_media(dict(PAGE_ITEM, username="<script>")) is None


def test_prefetch_checks_the_next_reel_before_you_reach_it(api, fakes):
    instagram_data._cache.clear()
    nxt = dict(PAGE_ITEM, code="NEXTreel99")
    r = api.post("/prefetch", json={"items": [nxt, {"code": "bad!"}]}).json()
    assert r["accepted"] == ["NEXTreel99"]
    import time as _t
    for _ in range(50):
        if fakes["listen"]:
            break
        _t.sleep(0.02)
    assert fakes["listen"] == 1                  # audio already being checked
    # arriving at that reel: nothing is fetched or listened to again
    v = api.post("/analyze", json={"page_url": "https://www.instagram.com/reels/NEXTreel99/",
                                   "is_reel": True, "transcribe": True}).json()
    assert fakes["listen"] == 1
    assert v["coverage"]["speech_read"] is True
    instagram_data._cache.clear()



def _score_for(api, fakes, monkeypatch, prob_fake=0.02, engagement=None, model=None, caption=None):
    async def predict_account(features):
        return {"available": True, "prob_fake": prob_fake, "band": "real" if prob_fake < 0.4 else "fake",
                "confidence": 0.9}
    monkeypatch.setattr(clients, "predict_account", predict_account)
    if engagement is not None:
        async def get_engagement(u):
            return dict(ENGAGEMENT, **engagement)
        monkeypatch.setattr(instagram_data, "get_engagement", get_engagement)
    if model is not None:
        async def classify_text(text):
            return {"available": True, "category": model["primary_category"],
                    "confidence": model["confidence"], "post_risk_score": model["risk_score"],
                    "red_flags": [], "model_result": dict(model)}
        monkeypatch.setattr(clients, "classify_text", classify_text)
    if caption is not None:
        async def get_media(code):
            return dict(MEDIA, code=code, caption=caption)
        monkeypatch.setattr(instagram_data, "get_media", get_media)
    return api.post("/analyze", json={"page_url": REEL, "is_reel": True, "transcribe": True}).json()


def test_badge_score_is_the_websites_trust_score_not_a_fixed_band(api, fakes, monkeypatch):
    import trust_score
    v = _score_for(api, fakes, monkeypatch)
    assert v["score_label"] in ("Trusted", "Moderate Risk", "High Risk")
    mods = v["trust_score"]["module_scores"]
    assert set(mods) >= {"fake_follower", "engagement", "misinformation"}
    # recompute with the website's own engine: same number
    expect = trust_score.calculate_trust_score(
        v["trust_score"]["bot_percentage"], mods["engagement"],
        {"status": "success", "risk_score": 100 - mods["misinformation"]},
        v["trust_score"]["credential"])["trust_score"]
    assert v["score"] == round(expect)
    assert abs(sum(b["weight"] for b in v["score_breakdown"]) - 100) < 0.01


def test_ordinary_reels_get_different_scores(api, fakes, monkeypatch):
    strong = _score_for(api, fakes, monkeypatch, prob_fake=0.01,
                        engagement={"avg_likes": 20000, "avg_comments": 400})
    instagram_data._cache.clear(); clients._classify_cache.clear(); clients._account_cache.clear()
    weak = _score_for(api, fakes, monkeypatch, prob_fake=0.30,
                      engagement={"avg_likes": 300, "avg_comments": 2})
    assert strong["score"] != weak["score"]
    assert strong["score"] > weak["score"]


def test_misinformation_in_the_reel_lowers_the_score(api, fakes, monkeypatch):
    clean = _score_for(api, fakes, monkeypatch)
    clients._classify_cache.clear()
    misinfo_model = {"status": "success", "primary_category": "health_misinformation",
                     "confidence": 0.9, "risk_score": 90,
                     "category_scores": {"credible": 0.05, "health_misinformation": 0.9,
                                         "financial_scam": 0.01, "political_propaganda": 0.02,
                                         "sensational_clickbait": 0.02}}
    bad = _score_for(api, fakes, monkeypatch, model=misinfo_model)
    assert bad["score"] < clean["score"] - 20
    assert bad["trust_score"]["module_scores"]["misinformation"] <= 20


def test_scam_post_is_red_and_its_number_agrees(api, fakes, monkeypatch):
    async def scam(text):
        return {"available": True, "category": "financial_scam", "category_label": "Financial Scam",
                "confidence": 0.99, "post_risk_score": 100,
                "red_flags": [{"type": "financial_promise", "severity": "high"},
                              {"type": "impossible_claim", "severity": "high"}],
                "model_result": {"status": "success", "primary_category": "financial_scam",
                                 "confidence": 0.99, "risk_score": 99,
                                 "category_scores": {"financial_scam": 0.99, "credible": 0.01}}}
    monkeypatch.setattr(clients, "classify_text", scam)
    v = _score_for(api, fakes, monkeypatch,
                   caption="GUARANTEED 300% profit in 7 days, DM me to invest")
    assert v["level"] == "danger"
    assert v["score"] < 40 and v["score_label"] == "High Risk"



def test_unclear_speech_is_shown_but_never_scored(api, fakes, monkeypatch):
    monkeypatch.setattr(reel_audio, "transcribe", lambda c, u, p, o=True: {
        "available": True, "text": "The elections are in this situation.", "no_speech": False,
        "language": "en", "confidence": 0.28, "quality": "rough", "is_reliable": False})
    v = api.post("/analyze", json={"page_url": REEL, "is_reel": True, "transcribe": True}).json()
    assert "speech" not in v["text_sources"]
    assert "elections" not in v["text_analyzed"]
    assert v["transcript"]["not_counted"] is True
    assert v["coverage"]["speech_read"] is True        # it WAS listened to
    assert any("unclear" in n for n in v["not_checked"])


# --------------------------------------------------------------------------- #
# 2026-09-28: shared models, "Scan this reel" warm-up, audio-only track
# --------------------------------------------------------------------------- #
import asyncio  # noqa: E402

import httpx  # noqa: E402


def test_model_service_moves_on_only_when_nothing_is_listening(monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

        async def post(self, url, json=None):
            calls.append(url)
            if url.startswith("http://first"):
                raise httpx.ConnectError("refused")
            return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(clients.httpx, "AsyncClient", FakeClient)
    svc = clients._Service("x", ["http://first", "http://second"])
    r = asyncio.run(svc.post("/check-text", {}, 5))
    assert r.status_code == 200 and svc.current == "http://second"
    calls.clear()
    asyncio.run(svc.post("/check-text", {}, 5))
    assert calls == ["http://second/check-text"]      # remembered, no retrying the dead one


def test_default_model_addresses_prefer_the_shared_website_copy(monkeypatch):
    import config
    assert config._urls("", ["http://a", "http://b"]) == ["http://a", "http://b"]
    # an old .env pointing at 8001 is tried first but the others stay as fallbacks
    assert config._urls("http://127.0.0.1:8001", ["http://w", "http://127.0.0.1:8001"]) == \
        ["http://127.0.0.1:8001", "http://w"]


def test_warm_fetches_data_but_never_runs_a_model(api, fakes):
    instagram_data._cache.clear()
    r = api.post("/warm", json={"page_url": REEL, "username": "real_creator"}).json()
    assert r["warming"] == "ABCdef123"
    import time as _t
    for _ in range(50):
        if fakes.get("engagement"):
            break
        _t.sleep(0.02)
    assert fakes["profile"] == ["real_creator"] and fakes["engagement"] == ["real_creator"]
    assert fakes["listen"] == 0 and fakes["predict"] == [] and fakes["classify"] == []


def test_audio_track_is_heard_first_and_the_video_is_the_fallback(monkeypatch):
    reel_audio._cache.clear()
    tried = []

    def fake_once(url, code, on_screen, progress, started):
        tried.append(url)
        if "audio" in url:
            raise RuntimeError("audio track wouldn't decode")
        return {"available": True, "text": "hi", "no_speech": False, "is_reliable": True}

    monkeypatch.setattr(reel_audio, "_listen_once", fake_once)
    monkeypatch.setattr(reel_audio, "_IMPORT_ERROR", None)
    r = reel_audio.transcribe("Zz1", ["https://x.cdninstagram.com/audio.mp4",
                                      "https://x.cdninstagram.com/video.mp4"], lambda *a: None)
    assert tried == ["https://x.cdninstagram.com/audio.mp4", "https://x.cdninstagram.com/video.mp4"]
    assert r["available"] and r["via"] == "video file"
    reel_audio._cache.clear()


def test_listen_urls_put_the_small_audio_track_first():
    assert main._listen_urls({"audio_url": "A", "video_url": "V"}) == ["A", "V"]
    assert main._listen_urls({"video_url": "V"}) == ["V"]


def test_audio_link_from_the_page_gets_the_same_host_check():
    item = instagram_data.clean_page_media(dict(PAGE_ITEM, audio_url="https://evil.example/a.mp4"))
    assert item["audio_url"] == ""
    item = instagram_data.clean_page_media(dict(PAGE_ITEM, audio_url="https://scontent.cdninstagram.com/a.mp4"))
    assert item["audio_url"].endswith("/a.mp4")


def test_badge_verdict_combines_flags_from_every_text():
    a = {"available": True, "post_risk_score": 10, "category": "credible",
         "red_flags": [{"type": "urgency", "detail": "x"}]}
    b = {"available": True, "post_risk_score": 90, "category": "financial_scam",
         "red_flags": [{"type": "financial_promise", "detail": "y"}]}
    c = main._combine([a, b])
    assert c["category"] == "financial_scam"
    assert {f["type"] for f in c["red_flags"]} == {"urgency", "financial_promise"}
