"""
Tests for the modules completed on 2026-09-28: score confidence + review label
(Module 8), watchlist/alerts, creator tools, brand API keys, CSV/PDF export
(Module 1), comparison PDF (Module 10), timeline + chart summaries (Module 9).

Throwaway SQLite file, never the real trustlens.db; Instagram is never called
(the pipeline's analyze_username is replaced by a fake built from the REAL
scoring functions, so scores and confidence are computed the real way).
"""
import json
import os
import tempfile
from datetime import datetime, timedelta

_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="trustlens_test_dash_"), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-anywhere-real")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import scan_service  # noqa: E402
import chart_explainer  # noqa: E402
from auth import create_token, hash_password  # noqa: E402
from database import SessionLocal, User, ScanHistory, Alert  # noqa: E402
from score_confidence import assess_confidence  # noqa: E402
from trust_score import calculate_trust_score  # noqa: E402

client = TestClient(main.app)
_n = [0]


def _user(role="user"):
    _n[0] += 1
    db = SessionLocal()
    u = User(full_name="Test Person", email=f"dash{_n[0]}@example.com", password_hash=hash_password("pass word 42"),
             email_verified=True, role=role, is_active=True)
    db.add(u)
    db.commit()
    uid = u.id
    db.close()
    return uid


def _auth(uid):
    return {"Authorization": f"Bearer {create_token(uid)}"}


def fake_result(username="some.creator", bot=5.0, engagement=80.0, misinfo_risk=10, posts=12,
                followers=50_000, likes=None, bio="Travel and food", corroborated=False, conf=0.95):
    mi = {"status": "success", "risk_score": misinfo_risk, "misinformation_flag": misinfo_risk >= 50,
          "primary_category": "credible" if misinfo_risk < 50 else "financial_scam",
          "confidence": conf, "corroborated": corroborated}
    eng_score = engagement if posts else None
    ts = calculate_trust_score(bot, eng_score, mi, None)
    likes = likes or [1000 + 10 * i for i in range(posts)]
    result = {
        "username": username, "full_name": "Some Creator", "is_verified": False,
        "raw_profile_data": {"username": username, "followers": followers, "following": 300, "posts": 120,
                             "biography": bio, "has_profile_pic": 1, "bio_length": len(bio)},
        "engagement_data": {"posts_analyzed": posts, "avg_likes": 1000, "avg_comments": 20,
                            "posts": [{"code": f"P{i}", "likes": v, "comments": 20} for i, v in enumerate(likes)]},
        "fake_follower_analysis": {"bot_percentage": bot, "verdict": "Low Risk"},
        "engagement_analysis": {"engagement_score": eng_score, "engagement_rate": 2.1, "benchmark": 3.0,
                                "tier": "Micro", "status": "Healthy", "color": "green", "like_comment_ratio": 50},
        "comment_authenticity": {"verdict": "Comments show healthy diversity", "comment_diversity_score": 80},
        "credential_analysis": {"claims_found": [], "confidence_score": None},
        "misinformation_analysis": mi,
        "misinformation_sources": [dict(mi, source="bio", text_preview=bio)],
        "trust_score": ts,
    }
    result["confidence"] = assess_confidence(result)
    return result


@pytest.fixture
def scans(monkeypatch):
    """Queue of fake results the pipeline will return, in order."""
    queue = []

    def fake_analyze(username):
        r = queue.pop(0) if queue else fake_result(username)
        r = json.loads(json.dumps(r))
        r["username"] = username
        return r
    monkeypatch.setattr(scan_service, "analyze_username", fake_analyze)
    return queue


# --------------------------------------------------------------------------- #
# Module 8: confidence and the review label
# --------------------------------------------------------------------------- #
def test_confident_scan_with_all_evidence_is_high():
    c = fake_result(bot=2, conf=0.97)["confidence"]
    assert c["label"] == "High" and c["confidence"] >= 80 and c["coverage"] == 100
    assert not c["uncertain"]


def test_missing_evidence_lowers_confidence_and_says_why():
    full = fake_result(bot=2)["confidence"]
    no_posts = fake_result(bot=2, posts=0)["confidence"]
    assert no_posts["coverage"] < 100
    assert no_posts["confidence"] < full["confidence"]
    assert any(m["module"] == "engagement" for m in no_posts["missing"])


def test_coin_flip_model_output_is_uncertain():
    c = fake_result(bot=50, conf=0.5, posts=3)["confidence"]
    assert c["uncertain"] and c["label"] == "Uncertain" and c["confidence"] < 60


def test_scores_between_35_and_55_require_review():
    for score, expected in [(34.9, False), (35, True), (45, True), (55, True), (55.1, False)]:
        r = fake_result()
        r["trust_score"]["trust_score"] = score
        assert assess_confidence(r)["needs_review"] is expected, score


def test_every_live_scan_carries_confidence(scans):
    uid = _user()
    r = client.post("/analyze-live", json={"username": "abc"}, headers=_auth(uid)).json()
    assert "confidence" in r and 0 <= r["confidence"]["confidence"] <= 100
    saved = client.get(f"/scans/{r['scan_id']}", headers=_auth(uid)).json()
    assert saved["confidence"]["confidence"] == r["confidence"]["confidence"]


def test_old_scans_get_confidence_when_reopened():
    uid = _user()
    old = fake_result()
    del old["confidence"]
    db = SessionLocal()
    s = ScanHistory(user_id=uid, username="old.one", trust_score=old["trust_score"]["trust_score"],
                    verdict=old["trust_score"]["verdict"], color="green", raw_result=json.dumps(old))
    db.add(s)
    db.commit()
    sid = s.id
    db.close()
    assert "confidence" in client.get(f"/scans/{sid}", headers=_auth(uid)).json()


# --------------------------------------------------------------------------- #
# Module 1: watchlist and alerts
# --------------------------------------------------------------------------- #
def test_watching_starts_from_your_latest_scan_and_alerts_on_a_drop(scans):
    uid = _user()
    scans.append(fake_result(bot=2, engagement=90, misinfo_risk=0))
    first = client.post("/analyze-live", json={"username": "watched.acc"}, headers=_auth(uid)).json()
    entry = client.post("/watchlist", json={"username": "@Watched.Acc"}, headers=_auth(uid)).json()
    assert entry["username"] == "watched.acc"
    assert entry["baseline_score"] == first["trust_score"]["trust_score"]

    # Small wobble in the same band: no alert.
    scans.append(fake_result(bot=4, engagement=88, misinfo_risk=0))
    client.post(f"/watchlist/{entry['id']}/recheck", headers=_auth(uid))
    assert client.get("/alerts", headers=_auth(uid)).json()["items"] == []

    # Real drop: alert.
    scans.append(fake_result(bot=60, engagement=30, misinfo_risk=90, corroborated=True))
    r = client.post(f"/watchlist/{entry['id']}/recheck", headers=_auth(uid)).json()
    assert r["entry"]["last_score"] < entry["baseline_score"] - 5
    alerts = client.get("/alerts", headers=_auth(uid)).json()
    assert alerts["unread"] == 1
    a = alerts["items"][0]
    assert a["username"] == "watched.acc" and a["new_score"] < a["old_score"]

    client.post("/alerts/read", headers=_auth(uid))
    assert client.get("/alerts", headers=_auth(uid)).json()["unread"] == 0


def test_a_small_drop_that_crosses_into_a_worse_band_still_alerts():
    from watchlist import is_drop
    assert is_drop(71, "Trusted", 69, "Moderate Risk")
    assert not is_drop(80, "Trusted", 77, "Trusted")
    assert is_drop(80, "Trusted", 74, "Trusted")


def test_watchlist_is_private_to_its_owner(scans):
    a, b = _user(), _user()
    entry = client.post("/watchlist", json={"username": "someone"}, headers=_auth(a)).json()
    assert client.delete(f"/watchlist/{entry['id']}", headers=_auth(b)).status_code == 404
    assert client.post(f"/watchlist/{entry['id']}/recheck", headers=_auth(b)).status_code == 404
    assert client.get("/watchlist", headers=_auth(b)).json()["items"] == []
    assert client.delete(f"/watchlist/{entry['id']}", headers=_auth(a)).status_code == 200


def test_watchlist_rejects_bad_usernames():
    uid = _user()
    assert client.post("/watchlist", json={"username": ""}, headers=_auth(uid)).status_code == 400
    assert client.post("/watchlist", json={"username": "x" * 31}, headers=_auth(uid)).status_code == 400


def test_background_recheck_round_scans_due_accounts(scans):
    from watchlist import recheck_round
    uid = _user()
    entry = client.post("/watchlist", json={"username": "due.acc"}, headers=_auth(uid)).json()
    assert entry["last_checked_at"] is None
    assert recheck_round() >= 1
    after = [e for e in client.get("/watchlist", headers=_auth(uid)).json()["items"] if e["id"] == entry["id"]][0]
    assert after["last_score"] is not None


# --------------------------------------------------------------------------- #
# Module 1: account types
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Module 1: brand tools — API keys, bulk source, CSV export
# --------------------------------------------------------------------------- #



def test_csv_export_has_the_comparison_metrics(scans):
    uid = _user()
    ids = [client.post("/analyze-live", json={"username": u}, headers=_auth(uid)).json()["scan_id"]
           for u in ("one", "two")]
    r = client.get(f"/exports/scans.csv?ids={ids[0]},{ids[1]}", headers=_auth(uid))
    assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
    lines = r.text.lstrip("﻿").strip().splitlines()
    assert len(lines) == 3
    for col in ("trust_score", "confidence_pct", "misinformation_flag_count", "credential_confidence",
                "fake_account_likelihood_pct", "requires_review"):
        assert col in lines[0]


# --------------------------------------------------------------------------- #
# PDFs: scan report (Module 1), comparison (Module 10)
# --------------------------------------------------------------------------- #
def test_scan_and_comparison_pdfs_are_real_pdfs(scans):
    uid = _user()
    ids = [client.post("/analyze-live", json={"username": u}, headers=_auth(uid)).json()["scan_id"]
           for u in ("alpha", "beta", "gamma")]
    one = client.get(f"/reports/scan/{ids[0]}.pdf", headers=_auth(uid))
    assert one.status_code == 200 and one.content.startswith(b"%PDF") and len(one.content) > 5000
    cmp = client.post("/reports/compare.pdf", json={"scan_ids": ids}, headers=_auth(uid))
    assert cmp.status_code == 200 and cmp.content.startswith(b"%PDF")
    assert client.post("/reports/compare.pdf", json={"scan_ids": ids[:1]}, headers=_auth(uid)).status_code == 400


def test_you_cannot_export_someone_elses_scan(scans):
    a, b = _user(), _user()
    sid = client.post("/analyze-live", json={"username": "priv"}, headers=_auth(a)).json()["scan_id"]
    assert client.get(f"/reports/scan/{sid}.pdf", headers=_auth(b)).status_code == 404
    assert client.post("/reports/compare.pdf", json={"scan_ids": [sid, sid]}, headers=_auth(b)).status_code == 404
    assert client.get(f"/exports/scans.csv?ids={sid}", headers=_auth(b)).text.lstrip("﻿").strip().count("\n") == 0


# --------------------------------------------------------------------------- #
# Module 1: creator tools
# --------------------------------------------------------------------------- #





# --------------------------------------------------------------------------- #
# Module 9: follower timeline and chart summaries
# --------------------------------------------------------------------------- #
def test_timeline_flags_follower_jumps_and_collapses_same_day_scans():
    uid = _user()
    db = SessionLocal()
    base = datetime(2026, 9, 1, 12)
    for days, followers in [(0, 1000), (0, 1010), (3, 1050), (6, 1400)]:
        db.add(ScanHistory(user_id=uid, username="grower", trust_score=70, verdict="Trusted", color="green",
                           followers=followers, raw_result="{}", scanned_at=base + timedelta(days=days, hours=len(str(followers)))))
    db.commit()
    db.close()
    t = client.get("/accounts/grower/timeline", headers=_auth(uid)).json()
    assert [p["followers"] for p in t["points"]] == [1010, 1050, 1400]
    assert len(t["anomalies"]) == 1 and t["anomalies"][0]["to"] == 1400


def test_chart_summaries_fall_back_to_rules_without_gemini(scans, monkeypatch):
    monkeypatch.setattr(chart_explainer, "_gemini_settings", lambda: ("", "none"))
    uid = _user()
    sid = client.post("/analyze-live", json={"username": "explained"}, headers=_auth(uid)).json()["scan_id"]
    r = client.post(f"/scans/{sid}/explain", headers=_auth(uid)).json()
    assert r["source"] == "rules"
    assert {"gauge", "radar", "trend", "timeline"} <= set(r["summaries"])
    assert all(isinstance(v, str) and v for v in r["summaries"].values())


def test_each_chart_is_labelled_with_who_wrote_it(monkeypatch):
    monkeypatch.setattr(chart_explainer, "_ask_gemini", lambda facts, keys: {"gauge": "only one"})
    r = chart_explainer.explain_charts(fake_result())
    assert r["summaries"]["gauge"] == "only one" and r["sources"]["gauge"] == "gemini"
    assert all(r["sources"][k] == "rules" and r["summaries"][k] for k in r["summaries"] if k != "gauge")
    assert r["source"] == "mixed"
    monkeypatch.setattr(chart_explainer, "_ask_gemini", lambda facts, keys: {k: f"about {k}" for k in keys})
    assert chart_explainer.explain_charts(fake_result())["source"] == "gemini"


# --------------------------------------------------------------------------- #
# Comments turned off (found on a real scan, @raisa.creationz, 2026-09-29)
# --------------------------------------------------------------------------- #
def test_comments_turned_off_is_not_read_as_a_bot_signal():
    from engagement_analyzer import analyze_engagement
    off = analyze_engagement(419_361, 1526.8, 0, 7532, posts_analyzed=12, comments_off=True)
    on = analyze_engagement(419_361, 1526.8, 0, 7532, posts_analyzed=12, comments_off=False)
    assert off["like_comment_ratio"] is None and off["comments_off"] is True
    assert not any("comment" in f.lower() for f in off["flags"])
    assert any("comment" in f.lower() for f in on["flags"])        # a real zero is still flagged
    assert off["engagement_score"] == on["engagement_score"]       # the score itself never used comments


def test_comments_off_is_detected_only_from_instagrams_own_marker(monkeypatch):
    import data_ingestion

    class Resp:
        status_code = 200

        def __init__(self, nodes):
            self._nodes = nodes

        def json(self):
            return {"posts": [{"node": n} for n in self._nodes]}

    def run(nodes):
        monkeypatch.setattr(data_ingestion, "_post_with_retry", lambda *a, **k: Resp(nodes))
        return data_ingestion.fetch_engagement_data("x")

    off = [{"code": f"p{i}", "like_count": 100, "comment_count": 0, "commenting_disabled_for_viewer": True} for i in range(6)]
    assert run(off)["comments_off"] is True
    zero_no_marker = [{"code": f"p{i}", "like_count": 100, "comment_count": 0} for i in range(6)]
    assert run(zero_no_marker)["comments_off"] is False
    some_comments = off[:5] + [{"code": "p9", "like_count": 100, "comment_count": 4, "commenting_disabled_for_viewer": True}]
    assert run(some_comments)["comments_off"] is False



def test_gemini_answer_shapes_are_all_understood():
    keys = ["gauge", "radar"]
    pick = chart_explainer._pick_summaries
    assert pick({"gauge": "a", "radar": "b"}, keys) == {"gauge": "a", "radar": "b"}
    assert pick({"charts": {"gauge": "a", "radar": "b"}}, keys) == {"gauge": "a", "radar": "b"}
    assert pick([{"chart": "gauge", "text": "a"}, {"chart": "radar", "summary": "b"}], keys) == {"gauge": "a", "radar": "b"}
    assert pick("nonsense", keys) == {}
