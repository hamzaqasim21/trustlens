# ============================================================
# TrustLens — Brand / agency tools (Web Dashboard, brand role)
# ============================================================
#
# Scope document §10, Brand / Agency: "bulk analysis tools, Influencer
# Comparison Engine for side-by-side forensic reports, CSV and PDF export, and
# API access for integration into their own marketing platforms."
#
#   Bulk analysis  -> the Brand tools page runs the normal scan for each
#                     username in turn (source "bulk"), then exports them.
#   CSV export     -> GET /exports/scans.csv (insights.py)
#   PDF export     -> reports.py
#   API access     -> API keys below + POST /api/v1/analyze
#
# The scope calls the brand dashboard a "paid tier". TrustLens has no payment
# system, so these tools are simply open to brand accounts; there is nothing
# pretending to charge anyone.

import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db, User, ApiKey, ScanHistory

router = APIRouter()

MAX_KEYS = 5
API_SCANS_PER_DAY = 100      # per brand account, protects the shared RapidAPI quota
KEY_PREFIX = "tlk_"


def require_brand(user: User = Depends(get_current_user)) -> User:
    if (user.account_type or "personal") != "brand":
        raise HTTPException(403, "Brand tools are for brand / agency accounts. Switch your account type in Settings.")
    return user


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _key_payload(k):
    return {"id": k.id, "name": k.name, "prefix": k.prefix, "revoked": bool(k.revoked),
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None}


@router.get("/api-keys")
def list_keys(user: User = Depends(require_brand), db: Session = Depends(get_db)):
    keys = db.query(ApiKey).filter(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc()).all()
    return {"items": [_key_payload(k) for k in keys], "daily_limit": API_SCANS_PER_DAY}


@router.post("/api-keys")
def create_key(data: dict, user: User = Depends(require_brand), db: Session = Depends(get_db)):
    name = (data.get("name") or "").strip()[:60] or "API key"
    active = db.query(ApiKey).filter(ApiKey.user_id == user.id, ApiKey.revoked == False).count()  # noqa: E712
    if active >= MAX_KEYS:
        raise HTTPException(400, f"You can have up to {MAX_KEYS} active keys. Revoke one first.")
    key = KEY_PREFIX + secrets.token_urlsafe(30)
    row = ApiKey(user_id=user.id, name=name, prefix=key[:10], key_hash=_hash(key))
    db.add(row)
    db.commit()
    db.refresh(row)
    # The only time the key itself is ever returned.
    return {**_key_payload(row), "key": key}


@router.delete("/api-keys/{key_id}")
def revoke_key(key_id: int, user: User = Depends(require_brand), db: Session = Depends(get_db)):
    row = db.get(ApiKey, key_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "Key not found.")
    row.revoked = True
    db.commit()
    return {"ok": True}


def api_key_user(x_api_key: str = Header(None), db: Session = Depends(get_db)) -> User:
    if not x_api_key:
        raise HTTPException(401, "Send your key in the X-API-Key header.")
    row = db.query(ApiKey).filter(ApiKey.key_hash == _hash(x_api_key.strip())).first()
    if not row or row.revoked:
        raise HTTPException(401, "This API key is not valid or has been revoked.")
    user = db.get(User, row.user_id)
    if not user or not user.is_active:
        raise HTTPException(403, "The account that owns this key is suspended.")
    if (user.account_type or "personal") != "brand":
        raise HTTPException(403, "API access belongs to brand accounts.")
    row.last_used_at = datetime.utcnow()
    db.commit()
    return user


@router.post("/api/v1/analyze")
def api_analyze(data: dict, user: User = Depends(api_key_user), db: Session = Depends(get_db)):
    """Same pipeline, same result JSON as the website's scan."""
    from scan_service import run_scan, ScanFailed
    since = datetime.utcnow() - timedelta(days=1)
    used = (db.query(ScanHistory)
            .filter(ScanHistory.user_id == user.id, ScanHistory.source == "api",
                    ScanHistory.scanned_at >= since).count())
    if used >= API_SCANS_PER_DAY:
        raise HTTPException(429, f"Daily API limit of {API_SCANS_PER_DAY} scans reached. Try again tomorrow.")
    try:
        return run_scan(db, user.id, data.get("username"), source="api")
    except ScanFailed as e:
        status = 404 if e.kind == "not_found" else 400 if e.kind == "invalid" else 502
        raise HTTPException(status, str(e))


@router.get("/api/v1/scans/{scan_id}")
def api_get_scan(scan_id: int, user: User = Depends(api_key_user), db: Session = Depends(get_db)):
    import json
    scan = db.get(ScanHistory, scan_id)
    if not scan or scan.user_id != user.id:
        raise HTTPException(404, "Scan not found.")
    result = json.loads(scan.raw_result)
    result["scan_id"] = scan.id
    return result
