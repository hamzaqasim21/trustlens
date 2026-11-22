"""
Tests for the dashboard features added on 2026-09-28: watchlist and alerts,
CSV/PDF export (Module 1), the comparison PDF (Module 10), and the
comments-turned-off fix, and the Creator / Brand account types. (The confidence and chart tests were archived with
those features in backend/archive/charts_and_confidence/.)

Throwaway SQLite file, never the real trustlens.db; Instagram is never called
(the pipeline's analyze_username is replaced by a fake built from the REAL
scoring functions, so scores are computed the real way).
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
import creator as creator_mod  # noqa: E402
from auth import create_token, hash_password  # noqa: E402
from database import SessionLocal, User, ScanHistory, Alert  # noqa: E402
from trust_score import calculate_trust_score  # noqa: E402

client = TestClient(main.app)
_n = [0]


def _user(role="user", account_type="personal"):
    _n[0] += 1
    db = SessionLocal()
    u = User(full_name="Test Person", email=f"dash{_n[0]}@example.com", password_hash=hash_password("pass word 42"),
             email_verified=True, role=role, is_active=True, account_type=account_type)
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
    return result


@pytest.fixture
def scans(monkeypatch):
    """Queue of fake results the pipeline will return, in order."""
    queue = []

    def fake_analyze(username, focus=None):
        r = queue.pop(0) if queue else fake_result(username)
        r = json.loads(json.dumps(r))
        r["username"] = username
        return r
    monkeypatch.setattr(scan_service, "analyze_username", fake_analyze)
    return queue


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
# CSV export
# --------------------------------------------------------------------------- #



def test_csv_export_has_the_comparison_metrics(scans):
    uid = _user()
    ids = [client.post("/analyze-live", json={"username": u}, headers=_auth(uid)).json()["scan_id"]
           for u in ("one", "two")]
    r = client.get(f"/exports/scans.csv?ids={ids[0]},{ids[1]}", headers=_auth(uid))
    assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
    lines = r.text.lstrip("﻿").strip().splitlines()
    assert len(lines) == 3
    for col in ("trust_score", "misinformation_flag_count", "credential_confidence",
                "fake_account_likelihood_pct"):
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


# --------------------------------------------------------------------------- #
# Account types: Creator studio and Brand tools (Module 1, scope §10)
# --------------------------------------------------------------------------- #
def test_account_type_can_be_changed_and_is_validated():
    uid = _user()
    assert client.get("/me", headers=_auth(uid)).json()["account_type"] == "personal"
    assert client.patch("/me", json={"account_type": "brand"}, headers=_auth(uid)).json()["account_type"] == "brand"
    assert client.patch("/me", json={"account_type": "king"}, headers=_auth(uid)).status_code == 400
    assert client.patch("/me", json={}, headers=_auth(uid)).status_code == 400


def test_api_keys_are_for_brands_only():
    assert client.get("/api-keys", headers=_auth(_user(account_type="personal"))).status_code == 403
    assert client.get("/api-keys", headers=_auth(_user(account_type="creator"))).status_code == 403


def test_api_key_lifecycle(scans):
    uid = _user(account_type="brand")
    made = client.post("/api-keys", json={"name": "CRM"}, headers=_auth(uid)).json()
    key = made["key"]
    assert key.startswith("tlk_") and made["prefix"] == key[:10]
    listed = client.get("/api-keys", headers=_auth(uid)).json()["items"]
    assert all("key" not in k for k in listed)   # never shown again

    assert client.post("/api/v1/analyze", json={"username": "x"}).status_code == 401
    assert client.post("/api/v1/analyze", json={"username": "x"}, headers={"X-API-Key": "tlk_wrong"}).status_code == 401
    r = client.post("/api/v1/analyze", json={"username": "api.target"}, headers={"X-API-Key": key})
    assert r.status_code == 200 and r.json()["trust_score"]["trust_score"] is not None
    db = SessionLocal()
    assert db.get(ScanHistory, r.json()["scan_id"]).source == "api"
    db.close()
    assert client.get(f"/api/v1/scans/{r.json()['scan_id']}", headers={"X-API-Key": key}).status_code == 200

    client.delete(f"/api-keys/{made['id']}", headers=_auth(uid))
    assert client.post("/api/v1/analyze", json={"username": "x"}, headers={"X-API-Key": key}).status_code == 401


def test_bulk_source_is_only_recorded_for_brand_accounts(scans):
    brand, personal = _user(account_type="brand"), _user(account_type="personal")
    rb = client.post("/analyze-live", json={"username": "b1", "source": "bulk"}, headers=_auth(brand)).json()
    rp = client.post("/analyze-live", json={"username": "p1", "source": "bulk"}, headers=_auth(personal)).json()
    db = SessionLocal()
    assert db.get(ScanHistory, rb["scan_id"]).source == "bulk"
    assert db.get(ScanHistory, rp["scan_id"]).source == "web"
    db.close()


def test_creator_tools_are_for_creator_accounts():
    assert client.get("/creator", headers=_auth(_user(account_type="personal"))).status_code == 403


def test_creator_proves_ownership_with_a_bio_code_then_gets_a_verifiable_badge(scans, monkeypatch):
    uid = _user(account_type="creator")
    claim = client.post("/creator/claim", json={"username": "@My.Handle"}, headers=_auth(uid)).json()
    assert claim["username"] == "my.handle" and claim["code"].startswith("TL-") and claim["status"] == "pending"

    import data_ingestion
    bio = {"text": "just vibes"}
    monkeypatch.setattr(data_ingestion, "fetch_instagram_profile",
                        lambda u: {"username": u, "biography": bio["text"]})
    r = client.post("/creator/claim/verify", headers=_auth(uid)).json()
    assert r["verified"] is False and claim["code"] in r["message"]

    bio["text"] = f"just vibes {claim['code'].lower()}"
    assert client.post("/creator/claim/verify", headers=_auth(uid)).json()["verified"] is True

    # No scan yet: no badge.
    assert client.post("/creator/badge", headers=_auth(uid)).status_code == 400
    assert client.post("/creator/scan", headers=_auth(uid)).json()["scan_id"]

    home = client.get("/creator", headers=_auth(uid)).json()
    assert home["claim"]["username"] == "my.handle"
    assert home["audience"]["signals"] and home["audience"]["limits"]
    assert home["tips"]

    badge = client.post("/creator/badge", headers=_auth(uid)).json()
    assert badge["valid"] and badge["username"] == "my.handle"
    public = client.get(f"/badges/{badge['code']}").json()           # no login needed
    assert public["valid"] and public["trust_score"] == badge["trust_score"]
    assert client.get("/badges/NOTAREALCODE").status_code == 404
    pdf = client.get(f"/creator/badge/{badge['code']}.pdf", headers=_auth(uid))
    assert pdf.content.startswith(b"%PDF")
    # Only its owner can download the certificate file.
    assert client.get(f"/creator/badge/{badge['code']}.pdf", headers=_auth(_user(account_type="creator"))).status_code == 404


def test_badge_needs_a_recent_scan(scans, monkeypatch):
    uid = _user(account_type="creator")
    code = client.post("/creator/claim", json={"username": "stale"}, headers=_auth(uid)).json()["code"]
    import data_ingestion
    monkeypatch.setattr(data_ingestion, "fetch_instagram_profile", lambda u: {"biography": code})
    client.post("/creator/claim/verify", headers=_auth(uid))
    sid = client.post("/creator/scan", headers=_auth(uid)).json()["scan_id"]
    db = SessionLocal()
    db.get(ScanHistory, sid).scanned_at = datetime.utcnow() - timedelta(days=30)
    db.commit()
    db.close()
    assert client.post("/creator/badge", headers=_auth(uid)).status_code == 400


def test_tips_follow_what_the_scan_found():
    bad = fake_result(bot=80, engagement=10, misinfo_risk=90)
    bad["engagement_analysis"]["color"] = "red"
    areas = {t["area"] for t in creator_mod.improvement_tips(bad)}
    assert {"Account authenticity", "Engagement"} <= areas
    good = creator_mod.improvement_tips(fake_result(bot=2))
    assert [t["area"] for t in good] == ["Overall"]


def test_engagement_consistency_flags_a_spike():
    c = creator_mod.engagement_consistency([{"likes": v} for v in [100, 110, 95, 105, 2000, 98]])
    assert c["label"] != "Steady" and len(c["spike_posts"]) == 1
