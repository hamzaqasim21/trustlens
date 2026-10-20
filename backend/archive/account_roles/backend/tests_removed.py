# Tests for the archived role features, taken out of tests/test_dashboard_modules.py.
# They need creator.py/brand.py mounted in main.py and User.account_type back.

def test_account_type_can_be_changed_and_is_validated():
    uid = _user()
    assert client.get("/me", headers=_auth(uid)).json()["account_type"] == "personal"
    assert client.patch("/me", json={"account_type": "brand"}, headers=_auth(uid)).json()["account_type"] == "brand"
    assert client.patch("/me", json={"account_type": "king"}, headers=_auth(uid)).status_code == 400
    assert client.patch("/me", json={}, headers=_auth(uid)).status_code == 400


def test_api_keys_are_for_brands_only():
    assert client.get("/api-keys", headers=_auth(_user("personal"))).status_code == 403
    assert client.get("/api-keys", headers=_auth(_user("creator"))).status_code == 403


def test_api_key_lifecycle(scans):
    uid = _user("brand")
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
    brand, personal = _user("brand"), _user("personal")
    rb = client.post("/analyze-live", json={"username": "b1", "source": "bulk"}, headers=_auth(brand)).json()
    rp = client.post("/analyze-live", json={"username": "p1", "source": "bulk"}, headers=_auth(personal)).json()
    db = SessionLocal()
    assert db.get(ScanHistory, rb["scan_id"]).source == "bulk"
    assert db.get(ScanHistory, rp["scan_id"]).source == "web"
    db.close()


def test_creator_tools_are_for_creator_accounts():
    assert client.get("/creator", headers=_auth(_user("personal"))).status_code == 403


def test_creator_proves_ownership_with_a_bio_code_then_gets_a_verifiable_badge(scans, monkeypatch):
    uid = _user("creator")
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
    assert client.get(f"/creator/badge/{badge['code']}.pdf", headers=_auth(_user("creator"))).status_code == 404


def test_badge_needs_a_recent_scan(scans, monkeypatch):
    uid = _user("creator")
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
