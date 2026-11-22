# ============================================================
# TrustLens — Admin API
# ============================================================
#
# Implements the Admin role exactly as the scope document defines it (§10):
#
#   "Manages the entire platform including user account management, score
#    dispute review, misinformation database updates, model performance
#    monitoring, subscription management, and platform-wide analytics.
#    Reviews all appeal submissions within 48 hours."
#
#   user account management       -> /admin/users...
#   score dispute review (48 h)   -> /admin/appeals...
#   misinformation database       -> /admin/feedback/export (upheld disputes,
#     updates                        labelled with the module at fault — the
#                                    input to retraining)
#   model performance monitoring  -> /admin/models, /admin/health
#   platform-wide analytics       -> /admin/overview, /admin/scans
#   subscription management       -> NOT built. TrustLens has no paid tier,
#                                    so there is nothing to manage; a screen
#                                    for subscriptions that don't exist would
#                                    be fake.
#
# Every route here depends on require_admin, which checks the role on the
# server. Every action that changes something writes an AuditLog row.

import csv
import io
import json
import os
import sys
from datetime import datetime, timedelta

import requests
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from auth import require_admin
from database import get_db, User, ScanHistory, Appeal, AuditLog
from email_service import email_configured
from trust_score import verdict_for
import video_transcriber

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_CLASSIFIER_DIR = os.path.join(BACKEND_DIR, "misinfo_classifier", "api")
if _CLASSIFIER_DIR not in sys.path:
    sys.path.append(_CLASSIFIER_DIR)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

# Scope document: "Admin reviews the case within 48 hours".
APPEAL_SLA_HOURS = 48

# What an upheld dispute can blame. Mirrors the four modules that actually
# feed the Trust Score, plus "other" for a case none of them explains.
MODULES_AT_FAULT = {
    "fake_follower": "Account authenticity (fake-account model)",
    "engagement": "Engagement Analyzer",
    "misinformation": "Misinformation Classifier",
    "credential": "Credential Extractor",
    "other": "Other / not model-specific",
}


# ------------------------------------------------------------------------- #
# Helpers
# ------------------------------------------------------------------------- #
def _iso(dt):
    return dt.isoformat() if dt else None


def _log(db: Session, admin: User, action: str, target_type=None, target_id=None, **details):
    db.add(AuditLog(
        admin_id=admin.id if admin else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=json.dumps(details) if details else None,
    ))


def _sla(appeal: Appeal) -> dict:
    """Where a dispute stands against the 48-hour promise."""
    due = appeal.created_at + timedelta(hours=APPEAL_SLA_HOURS)
    if appeal.status != "pending":
        end = appeal.resolved_at or datetime.utcnow()
        return {
            "due_at": _iso(due),
            "hours_left": None,
            "overdue": False,
            "resolved_within_sla": end <= due,
        }
    hours_left = (due - datetime.utcnow()).total_seconds() / 3600
    return {
        "due_at": _iso(due),
        "hours_left": round(hours_left, 1),
        "overdue": hours_left < 0,
        "resolved_within_sla": None,
    }


def _page_args(page: int, page_size: int):
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    return page, page_size, (page - 1) * page_size


def _user_row(u: User, scan_count: int = 0) -> dict:
    return {
        "id": u.id,
        "full_name": u.full_name,
        "email": u.email,
        "role": u.role or "user",
        "is_active": u.is_active is not False,
        "email_verified": bool(u.email_verified),
        "created_at": _iso(u.created_at),
        "last_login_at": _iso(u.last_login_at),
        "scan_count": scan_count,
    }


def _scan_row(s: ScanHistory, owner_email=None) -> dict:
    return {
        "id": s.id,
        "username": s.username,
        "full_name": s.full_name,
        "is_verified": s.is_verified,
        "followers": s.followers,
        "trust_score": s.trust_score,
        "verdict": s.verdict,
        "color": s.color,
        "bot_percentage": s.bot_percentage,
        "engagement_score": s.engagement_score,
        "misinformation_flag": s.misinformation_flag,
        "corrected_trust_score": s.corrected_trust_score,
        "corrected_verdict": s.corrected_verdict,
        "user_id": s.user_id,
        "owner_email": owner_email,
        "scanned_at": _iso(s.scanned_at),
    }


def _appeal_row(a: Appeal, scan: ScanHistory, filer: User, resolver: User | None) -> dict:
    return {
        "id": a.id,
        "status": a.status,
        "reason": a.reason,
        "evidence_url": a.evidence_url,
        "created_at": _iso(a.created_at),
        "resolved_at": _iso(a.resolved_at),
        "admin_note": a.admin_note,
        "corrected_trust_score": a.corrected_trust_score,
        "module_at_fault": a.module_at_fault,
        "sla": _sla(a),
        "scan": _scan_row(scan) if scan else None,
        "filed_by": {"id": filer.id, "full_name": filer.full_name, "email": filer.email} if filer else None,
        "resolved_by": {"id": resolver.id, "full_name": resolver.full_name} if resolver else None,
    }


def _daily_counts(timestamps, days: int):
    """Counts per calendar day (UTC) for the last `days` days, zero-filled so
    a quiet day shows as 0 rather than silently disappearing from a chart."""
    today = datetime.utcnow().date()
    buckets = {today - timedelta(days=i): 0 for i in range(days - 1, -1, -1)}
    for ts in timestamps:
        if ts and ts.date() in buckets:
            buckets[ts.date()] += 1
    return [{"date": d.isoformat(), "count": c} for d, c in buckets.items()]


# ------------------------------------------------------------------------- #
# Platform-wide analytics
# ------------------------------------------------------------------------- #
@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    day_start = datetime(now.year, now.month, now.day)
    window_start = now - timedelta(days=14)

    total_users = db.query(func.count(User.id)).scalar()
    total_scans = db.query(func.count(ScanHistory.id)).scalar()

    verdicts = dict(
        db.query(ScanHistory.verdict, func.count(ScanHistory.id)).group_by(ScanHistory.verdict).all()
    )

    misinfo_checked = db.query(func.count(ScanHistory.id)).filter(ScanHistory.misinformation_flag.isnot(None)).scalar()
    misinfo_flagged = db.query(func.count(ScanHistory.id)).filter(ScanHistory.misinformation_flag.is_(True)).scalar()

    pending = db.query(Appeal).filter(Appeal.status == "pending").all()

    top = (
        db.query(ScanHistory.username, func.count(ScanHistory.id).label("n"))
        .group_by(ScanHistory.username)
        .order_by(func.count(ScanHistory.id).desc())
        .limit(5)
        .all()
    )
    top_accounts = []
    for username, n in top:
        latest = (
            db.query(ScanHistory)
            .filter(ScanHistory.username == username)
            .order_by(ScanHistory.scanned_at.desc())
            .first()
        )
        top_accounts.append({
            "username": username,
            "scans": n,
            "latest_score": latest.trust_score if latest else None,
            "latest_verdict": latest.verdict if latest else None,
        })

    recent = (
        db.query(AuditLog, User)
        .outerjoin(User, User.id == AuditLog.admin_id)
        .order_by(AuditLog.created_at.desc())
        .limit(8)
        .all()
    )

    return {
        "generated_at": _iso(now),
        "users": {
            "total": total_users,
            "verified": db.query(func.count(User.id)).filter(User.email_verified.is_(True)).scalar(),
            "suspended": db.query(func.count(User.id)).filter(User.is_active.is_(False)).scalar(),
            "admins": db.query(func.count(User.id)).filter(User.role == "admin").scalar(),
            "new_last_7_days": db.query(func.count(User.id)).filter(User.created_at >= week_ago).scalar(),
        },
        "scans": {
            "total": total_scans,
            "today": db.query(func.count(ScanHistory.id)).filter(ScanHistory.scanned_at >= day_start).scalar(),
            "last_7_days": db.query(func.count(ScanHistory.id)).filter(ScanHistory.scanned_at >= week_ago).scalar(),
            "by_logged_in_users": db.query(func.count(ScanHistory.id)).filter(ScanHistory.user_id.isnot(None)).scalar(),
            "anonymous": db.query(func.count(ScanHistory.id)).filter(ScanHistory.user_id.is_(None)).scalar(),
            "average_trust_score": round(db.query(func.avg(ScanHistory.trust_score)).scalar() or 0, 1) if total_scans else None,
            "verdicts": {
                "Trusted": verdicts.get("Trusted", 0),
                "Moderate Risk": verdicts.get("Moderate Risk", 0),
                "High Risk": verdicts.get("High Risk", 0),
            },
            "misinformation_flag_rate": round(100 * misinfo_flagged / misinfo_checked, 1) if misinfo_checked else None,
        },
        "appeals": {
            "pending": len(pending),
            "overdue": sum(1 for a in pending if _sla(a)["overdue"]),
            "upheld": db.query(func.count(Appeal.id)).filter(Appeal.status == "upheld").scalar(),
            "rejected": db.query(func.count(Appeal.id)).filter(Appeal.status == "rejected").scalar(),
        },
        "scans_per_day": _daily_counts(
            [r[0] for r in db.query(ScanHistory.scanned_at).filter(ScanHistory.scanned_at >= window_start).all()], 14
        ),
        "signups_per_day": _daily_counts(
            [r[0] for r in db.query(User.created_at).filter(User.created_at >= window_start).all()], 14
        ),
        "top_accounts": top_accounts,
        "recent_activity": [
            {
                "action": log.action,
                "admin": admin.full_name if admin else "Command line",
                "target_type": log.target_type,
                "target_id": log.target_id,
                "created_at": _iso(log.created_at),
            }
            for log, admin in recent
        ],
    }


# ------------------------------------------------------------------------- #
# User account management
# ------------------------------------------------------------------------- #
@router.get("/users")
def list_users(
    search: str = "",
    status: str = "all",
    page: int = 1,
    page_size: int = 25,
    db: Session = Depends(get_db),
):
    page, page_size, offset = _page_args(page, page_size)

    q = db.query(User)
    if search.strip():
        term = f"%{search.strip()}%"
        q = q.filter(or_(User.full_name.ilike(term), User.email.ilike(term)))

    if status == "verified":
        q = q.filter(User.email_verified.is_(True))
    elif status == "unverified":
        q = q.filter(User.email_verified.isnot(True))
    elif status == "suspended":
        q = q.filter(User.is_active.is_(False))
    elif status == "admins":
        q = q.filter(User.role == "admin")

    total = q.count()
    users = q.order_by(User.created_at.desc()).offset(offset).limit(page_size).all()

    counts = dict(
        db.query(ScanHistory.user_id, func.count(ScanHistory.id))
        .filter(ScanHistory.user_id.in_([u.id for u in users]))
        .group_by(ScanHistory.user_id)
        .all()
    ) if users else {}

    return {
        "items": [_user_row(u, counts.get(u.id, 0)) for u in users],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/users/{user_id}")
def user_detail(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    scans = (
        db.query(ScanHistory)
        .filter(ScanHistory.user_id == user.id)
        .order_by(ScanHistory.scanned_at.desc())
        .limit(50)
        .all()
    )
    appeals = (
        db.query(Appeal, ScanHistory)
        .join(ScanHistory, ScanHistory.id == Appeal.scan_id)
        .filter(Appeal.user_id == user.id)
        .order_by(Appeal.created_at.desc())
        .all()
    )
    history = (
        db.query(AuditLog, User)
        .outerjoin(User, User.id == AuditLog.admin_id)
        .filter(AuditLog.target_type == "user", AuditLog.target_id == user.id)
        .order_by(AuditLog.created_at.desc())
        .all()
    )

    return {
        "user": _user_row(user, len(scans)),
        "scans": [_scan_row(s) for s in scans],
        "appeals": [
            {
                "id": a.id,
                "status": a.status,
                "username": s.username,
                "original_score": s.trust_score,
                "corrected_trust_score": a.corrected_trust_score,
                "created_at": _iso(a.created_at),
            }
            for a, s in appeals
        ],
        "admin_history": [
            {
                "action": log.action,
                "admin": admin.full_name if admin else "Command line",
                "details": json.loads(log.details) if log.details else None,
                "created_at": _iso(log.created_at),
            }
            for log, admin in history
        ],
    }


def _get_other_user(db: Session, user_id: int, admin: User) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == admin.id:
        # Stops an admin locking themselves out of the only account that
        # could let them back in.
        raise HTTPException(400, "You can't change your own account from the admin panel.")
    return user


@router.post("/users/{user_id}/suspend")
def suspend_user(
    user_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = _get_other_user(db, user_id, admin)
    reason = (data.get("reason") or "").strip()
    if len(reason) < 5:
        raise HTTPException(400, "Give a reason for the suspension — it goes in the audit log.")
    if user.role == "admin":
        raise HTTPException(400, "Revoke this person's admin access before suspending them.")
    if user.is_active is False:
        raise HTTPException(409, "This account is already suspended.")

    user.is_active = False
    _log(db, admin, "user.suspend", "user", user.id, email=user.email, reason=reason)
    db.commit()
    return {"ok": True, "user": _user_row(user)}


@router.post("/users/{user_id}/reactivate")
def reactivate_user(
    user_id: int,
    data: dict | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = _get_other_user(db, user_id, admin)
    if user.is_active is not False:
        raise HTTPException(409, "This account isn't suspended.")

    user.is_active = True
    _log(db, admin, "user.reactivate", "user", user.id, email=user.email,
         reason=((data or {}).get("reason") or "").strip() or None)
    db.commit()
    return {"ok": True, "user": _user_row(user)}


@router.post("/users/{user_id}/role")
def change_role(
    user_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = _get_other_user(db, user_id, admin)
    role = data.get("role")
    if role not in ("user", "admin"):
        raise HTTPException(400, "Role must be 'user' or 'admin'.")
    if role == (user.role or "user"):
        raise HTTPException(409, f"This account is already a {role}.")
    if role == "admin" and (not user.email_verified or user.is_active is False):
        raise HTTPException(400, "Only verified, active accounts can be made admins.")

    old = user.role or "user"
    user.role = role
    _log(db, admin, "user.role_change", "user", user.id, email=user.email, from_role=old, to_role=role)
    db.commit()
    return {"ok": True, "user": _user_row(user)}


# ------------------------------------------------------------------------- #
# Scans, platform-wide
# ------------------------------------------------------------------------- #
@router.get("/scans")
def list_scans(
    search: str = "",
    verdict: str = "all",
    owner: str = "all",
    page: int = 1,
    page_size: int = 25,
    db: Session = Depends(get_db),
):
    page, page_size, offset = _page_args(page, page_size)

    q = db.query(ScanHistory, User).outerjoin(User, User.id == ScanHistory.user_id)
    if search.strip():
        q = q.filter(ScanHistory.username.ilike(f"%{search.strip().lstrip('@')}%"))
    if verdict in ("Trusted", "Moderate Risk", "High Risk"):
        q = q.filter(ScanHistory.verdict == verdict)
    if owner == "logged_in":
        q = q.filter(ScanHistory.user_id.isnot(None))
    elif owner == "anonymous":
        q = q.filter(ScanHistory.user_id.is_(None))
    elif owner == "corrected":
        q = q.filter(ScanHistory.corrected_trust_score.isnot(None))

    total = q.count()
    rows = q.order_by(ScanHistory.scanned_at.desc()).offset(offset).limit(page_size).all()

    return {
        "items": [_scan_row(s, u.email if u else None) for s, u in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/scans/{scan_id}")
def scan_detail(scan_id: int, db: Session = Depends(get_db)):
    scan = db.query(ScanHistory).filter(ScanHistory.id == scan_id).first()
    if not scan:
        raise HTTPException(404, "Scan not found")
    owner = db.query(User).filter(User.id == scan.user_id).first() if scan.user_id else None
    appeal = db.query(Appeal).filter(Appeal.scan_id == scan.id).first()

    try:
        raw = json.loads(scan.raw_result) if scan.raw_result else None
    except ValueError:
        raw = None

    return {
        "scan": _scan_row(scan, owner.email if owner else None),
        "owner": _user_row(owner) if owner else None,
        "appeal_id": appeal.id if appeal else None,
        "appeal_status": appeal.status if appeal else None,
        "result": raw,
    }


# ------------------------------------------------------------------------- #
# Score dispute review
# ------------------------------------------------------------------------- #
@router.get("/appeals")
def list_appeals(status: str = "pending", db: Session = Depends(get_db)):
    q = (
        db.query(Appeal, ScanHistory, User)
        .join(ScanHistory, ScanHistory.id == Appeal.scan_id)
        .join(User, User.id == Appeal.user_id)
    )
    if status in ("pending", "upheld", "rejected"):
        q = q.filter(Appeal.status == status)

    # Oldest pending first — that's the one closest to breaching 48 hours.
    order = Appeal.created_at.asc() if status == "pending" else Appeal.created_at.desc()
    rows = q.order_by(order).all()

    resolver_ids = {a.resolved_by for a, _, _ in rows if a.resolved_by}
    resolvers = {u.id: u for u in db.query(User).filter(User.id.in_(resolver_ids)).all()} if resolver_ids else {}

    return {
        "items": [_appeal_row(a, s, u, resolvers.get(a.resolved_by)) for a, s, u in rows],
        "sla_hours": APPEAL_SLA_HOURS,
        "modules": MODULES_AT_FAULT,
    }


@router.get("/appeals/{appeal_id}")
def appeal_detail(appeal_id: int, db: Session = Depends(get_db)):
    appeal = db.query(Appeal).filter(Appeal.id == appeal_id).first()
    if not appeal:
        raise HTTPException(404, "Dispute not found")
    scan = db.query(ScanHistory).filter(ScanHistory.id == appeal.scan_id).first()
    filer = db.query(User).filter(User.id == appeal.user_id).first()
    resolver = db.query(User).filter(User.id == appeal.resolved_by).first() if appeal.resolved_by else None

    try:
        raw = json.loads(scan.raw_result) if scan and scan.raw_result else None
    except ValueError:
        raw = None

    row = _appeal_row(appeal, scan, filer, resolver)
    row["result"] = raw
    row["modules"] = MODULES_AT_FAULT
    row["sla_hours"] = APPEAL_SLA_HOURS
    return row


@router.post("/appeals/{appeal_id}/resolve")
def resolve_appeal(
    appeal_id: int,
    data: dict,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    appeal = db.query(Appeal).filter(Appeal.id == appeal_id).first()
    if not appeal:
        raise HTTPException(404, "Dispute not found")
    if appeal.status != "pending":
        raise HTTPException(409, "This dispute has already been decided.")
    if appeal.user_id == admin.id:
        # Separation of duties: nobody rules on their own complaint.
        raise HTTPException(403, "You filed this dispute yourself, so another admin has to review it.")

    decision = data.get("decision")
    note = (data.get("note") or "").strip()
    if decision not in ("upheld", "rejected"):
        raise HTTPException(400, "Decision must be 'upheld' or 'rejected'.")
    if len(note) < 10:
        raise HTTPException(400, "Write a short explanation for the user (at least 10 characters) — they will see it.")

    scan = db.query(ScanHistory).filter(ScanHistory.id == appeal.scan_id).first()
    corrected = None
    module = None

    if decision == "upheld":
        try:
            corrected = round(float(data.get("corrected_trust_score")), 1)
        except (TypeError, ValueError):
            raise HTTPException(400, "Upholding a dispute needs the corrected score (0-100).")
        if not 0 <= corrected <= 100:
            raise HTTPException(400, "The corrected score must be between 0 and 100.")
        module = data.get("module_at_fault")
        if module not in MODULES_AT_FAULT:
            raise HTTPException(400, "Say which part of the analysis got it wrong — that's what makes the case usable for retraining.")

        scan.corrected_trust_score = corrected
        scan.corrected_verdict = verdict_for(corrected)[0]

    appeal.status = decision
    appeal.admin_note = note
    appeal.resolved_at = datetime.utcnow()
    appeal.resolved_by = admin.id
    appeal.corrected_trust_score = corrected
    appeal.module_at_fault = module

    _log(db, admin, "appeal.resolve", "appeal", appeal.id,
         decision=decision, scan_id=scan.id if scan else None, username=scan.username if scan else None,
         original_score=scan.trust_score if scan else None, corrected_score=corrected,
         module_at_fault=module, within_sla=_sla(appeal)["resolved_within_sla"])
    db.commit()

    filer = db.query(User).filter(User.id == appeal.user_id).first()
    return _appeal_row(appeal, scan, filer, admin)


# ------------------------------------------------------------------------- #
# Model performance monitoring + system health
# ------------------------------------------------------------------------- #
_FF_EVAL_CACHE = {"mtime": None, "result": None}


def _file_info(path):
    if not os.path.exists(path):
        return {"present": False}
    st = os.stat(path)
    return {
        "present": True,
        # Raw bytes; the page picks KB or MB. Rounding to MB here showed small
        # source files as "0 MB", which reads like an empty, broken file.
        "size_bytes": st.st_size,
        "modified_at": _iso(datetime.utcfromtimestamp(st.st_mtime)),
    }


def _evaluate_fake_follower():
    """Scores the live model against its held-out test set, right now.

    Cached against the model file's modification time, so it re-runs by
    itself after a retrain and is instant otherwise. This is a real
    measurement taken on request, not a number typed in from an earlier run.
    """
    from fake_follower import MODEL_PATH, _load_model
    if not os.path.exists(MODEL_PATH):
        return {"available": False, "error": "fake_follower_model.pkl is missing"}

    mtime = os.path.getmtime(MODEL_PATH)
    if _FF_EVAL_CACHE["mtime"] == mtime and _FF_EVAL_CACHE["result"]:
        return _FF_EVAL_CACHE["result"]

    try:
        import pandas as pd
        from sklearn.metrics import accuracy_score, precision_score, recall_score
        from fake_follower import FEATURE_NAMES
        from train_fake_follower import load_split

        X, y = load_split("test")
        pred = _load_model().predict(pd.DataFrame(X, columns=FEATURE_NAMES))
        result = {
            "available": True,
            "test_rows": int(len(y)),
            "accuracy": round(float(accuracy_score(y, pred)) * 100, 1),
            "precision": round(float(precision_score(y, pred)) * 100, 1),
            "recall": round(float(recall_score(y, pred)) * 100, 1),
            "evaluated_at": _iso(datetime.utcnow()),
        }
    except Exception as exc:
        result = {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    _FF_EVAL_CACHE.update(mtime=mtime, result=result)
    return result


@router.get("/models")
def models(db: Session = Depends(get_db)):
    try:
        import model_loader
        misinfo_loaded = getattr(model_loader, "_model", None) is not None
    except Exception:
        misinfo_loaded = False

    resolved = db.query(Appeal).filter(Appeal.status.in_(["upheld", "rejected"])).count()
    upheld = db.query(Appeal).filter(Appeal.status == "upheld").count()
    fault_counts = dict(
        db.query(Appeal.module_at_fault, func.count(Appeal.id))
        .filter(Appeal.status == "upheld")
        .group_by(Appeal.module_at_fault)
        .all()
    )

    return {
        "models": [
            {
                "key": "fake_follower",
                "name": "Account Authenticity",
                "kind": "Machine learning — Random Forest (supervised). Judges the account's own profile, not its followers.",
                "is_ml": True,
                "artifact": _file_info(os.path.join(BACKEND_DIR, "fake_follower_model.pkl")),
                "measurement": "live",
                "metrics": _evaluate_fake_follower(),
                "evaluated_on": "120 held-out test accounts the model never trained on",
                "source": "backend/train_fake_follower.py — held-out test split of the Kaggle 'Instagram fake spammer genuine accounts' dataset",
            },
            {
                "key": "misinformation",
                "name": "Misinformation Classifier",
                "kind": "Machine learning — fine-tuned XLM-RoBERTa (6 classes)",
                "is_ml": True,
                "artifact": _file_info(os.path.join(_CLASSIFIER_DIR, "model", "model.safetensors")),
                "loaded_in_memory": misinfo_loaded,
                "measurement": "recorded",
                "metrics": {"available": True, "accuracy": 77.0, "test_rows": 4640},
                "evaluated_on": "4,640 held-out test texts the model never trained on",
                "source": "Measured on a held-out test set at training time (Google Colab GPU). Re-running it needs a GPU, so it is shown as recorded, not re-measured here.",
            },
            {
                "key": "graph",
                "name": "Follower Graph Clustering",
                "kind": "Unsupervised — Manhattan distance + Louvain communities (offline)",
                "is_ml": True,
                "artifact": _file_info(os.path.join(BACKEND_DIR, "fake_follower_graph", "graph_cluster.py")),
                "measurement": "recorded",
                "metrics": {"available": True, "precision": 94.7, "recall": 38.9, "accuracy": 81.6, "test_rows": 1890},
                # Not "held-out": clustering is unsupervised, so nothing is
                # trained and nothing is held back. The labels are only used
                # afterwards, to score the clusters it found.
                "evaluated_on": "1,890 labelled accounts — unsupervised, so labels were used only to score the result",
                "source": "backend/fake_follower_graph/run_analysis.py — runs offline, not on live scans",
            },
            {
                "key": "video_to_text",
                "name": "Video-to-Text Transcriber",
                "kind": "Pretrained speech model — OpenAI Whisper (faster-whisper, CPU), used as-is. Its text is judged by the Misinformation Classifier.",
                "is_ml": True,
                "artifact": _whisper_artifact(),
                "loaded_in_memory": bool(video_transcriber._models),
                "measurement": "pretrained",
                "metrics": None,
                "source": "Listens to the first 45 s of the account's 3 newest reels on every scan (a pasted reel link is always one of them). Hindi-labelled speech is written out in Urdu script. Unclear speech is shown but never scored, Urdu speech only counts when a red-flag rule backs the model's label, and other languages are shown but not scored (the classifier was only trained on English and Urdu). No accuracy figure: it was not trained or tested by us.",
            },
            {
                "key": "engagement",
                "name": "Engagement Analyzer",
                "kind": "Rule-based (not machine learning)",
                "is_ml": False,
                "artifact": _file_info(os.path.join(BACKEND_DIR, "engagement_analyzer.py")),
                "measurement": "none",
                "metrics": None,
                "source": "Deterministic rules against follower-tier benchmarks — there is no trained accuracy to report.",
            },
            {
                "key": "credential",
                "name": "Credential Extractor",
                "kind": "Rule-based (not machine learning)",
                "is_ml": False,
                "artifact": _file_info(os.path.join(BACKEND_DIR, "credential_extractor.py")),
                "measurement": "none",
                "metrics": None,
                "source": "Pattern matching on the bio. Doctor claims (Dr., MBBS, MD) are looked up by name in the PMDC (Pakistan) and US NPI public registers; other claims have no free public register and are not scored.",
            },
            {
                "key": "trust_score",
                "name": "Trust Score Engine",
                "kind": "Weighted formula (not machine learning)",
                "is_ml": False,
                "artifact": _file_info(os.path.join(BACKEND_DIR, "trust_score.py")),
                "measurement": "none",
                "metrics": None,
                "source": "Scope-document weights (25/20/25/10), re-normalised to 100% across whichever modules apply.",
            },
        ],
        # The only real-world error signal available: cases where a person
        # looked at the evidence and decided the score was wrong. Test-set
        # accuracy says how a model did on a benchmark; this says how the
        # whole product did on real disputes.
        "field_feedback": {
            "disputes_resolved": resolved,
            "disputes_upheld": upheld,
            "overturn_rate": round(100 * upheld / resolved, 1) if resolved else None,
            "upheld_by_module": {k: fault_counts.get(k, 0) for k in MODULES_AT_FAULT},
        },
    }


def _whisper_artifact():
    """The quick speech model's weights file (shared with the extension)."""
    import glob
    hits = glob.glob(os.path.join(str(video_transcriber.MODELS_DIR),
                                  f"models--Systran--faster-whisper-{video_transcriber.QUICK_MODEL}",
                                  "snapshots", "*", "model.bin"))
    return _file_info(hits[0]) if hits else {"present": False}


@router.get("/health")
def health(db: Session = Depends(get_db)):
    checks = []

    try:
        db.execute(text("SELECT 1"))
        checks.append({"name": "Database", "ok": True, "detail": "Connected and answering queries"})
    except Exception as exc:
        checks.append({"name": "Database", "ok": False, "detail": f"{type(exc).__name__}"})

    # Configured-or-not only. The values themselves never leave the server.
    checks.append({
        "name": "Email (verification codes)",
        "ok": email_configured(),
        "detail": "Gmail sender configured" if email_configured() else "GMAIL_ADDRESS / GMAIL_APP_PASSWORD missing from .env",
    })
    checks.append({
        "name": "Instagram data (RapidAPI)",
        "ok": bool(os.getenv("RAPIDAPI_KEY")),
        "detail": "API key configured" if os.getenv("RAPIDAPI_KEY") else "RAPIDAPI_KEY missing from .env — live scans will fail",
    })
    checks.append({
        "name": "Login tokens (JWT)",
        "ok": bool(os.getenv("JWT_SECRET")),
        "detail": "Signing secret configured" if os.getenv("JWT_SECRET") else "JWT_SECRET missing from .env",
    })

    ff = os.path.join(BACKEND_DIR, "fake_follower_model.pkl")
    checks.append({
        "name": "Fake follower model file",
        "ok": os.path.exists(ff),
        "detail": "Present" if os.path.exists(ff) else "Missing — run train_fake_follower.py",
    })
    mi = os.path.join(_CLASSIFIER_DIR, "model", "model.safetensors")
    checks.append({
        "name": "Misinformation model file",
        "ok": os.path.exists(mi),
        "detail": "Present" if os.path.exists(mi) else "Missing — it is not in the repo (1.1 GB); see misinfo_classifier/README.md",
    })

    w = video_transcriber.status()
    checks.append({
        "name": "Speech model (reel transcription)",
        "ok": bool(w.get("available")) and _whisper_artifact()["present"],
        "detail": (f"{w['quick_model']} loaded" if w.get("loaded") else "Present, loads on first use")
        if w.get("available") and _whisper_artifact()["present"]
        else f"Not available — {w.get('error') or 'model files missing; first scan downloads ~150 MB'}",
    })

    try:
        r = requests.get("http://127.0.0.1:8100/health", timeout=2)
        up = r.status_code < 400
        checks.append({
            "name": "Browser extension gateway",
            "ok": up,
            "optional": True,
            "detail": "Running on :8100" if up else f"Answered with HTTP {r.status_code}",
        })
    except Exception:
        checks.append({
            "name": "Browser extension gateway",
            "ok": False,
            "optional": True,
            "detail": "Not running — only needed while using the Chrome extension",
        })

    return {"checked_at": _iso(datetime.utcnow()), "checks": checks}


# ------------------------------------------------------------------------- #
# Feedback loop — "misinformation database updates"
# ------------------------------------------------------------------------- #
@router.get("/feedback/export")
def export_feedback(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Every upheld dispute as a labelled CSV.

    Scope document, Layer 5: "Disputed and corrected scores are logged and
    used to retrain the AI models monthly." This is that log, in a form a
    retraining script can read. Retraining itself stays a deliberate offline
    step — nothing here silently changes a model.
    """
    rows = (
        db.query(Appeal, ScanHistory)
        .join(ScanHistory, ScanHistory.id == Appeal.scan_id)
        .filter(Appeal.status == "upheld")
        .order_by(Appeal.resolved_at.asc())
        .all()
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "appeal_id", "scan_id", "username", "scanned_at", "resolved_at",
        "original_score", "original_verdict", "corrected_score", "corrected_verdict",
        "module_at_fault", "bot_percentage", "engagement_score",
        "misinfo_model_category", "misinfo_text_preview", "admin_note",
    ])
    for a, s in rows:
        category, preview = "", ""
        try:
            misinfo = (json.loads(s.raw_result) or {}).get("misinformation_analysis") or {}
            category = misinfo.get("primary_category") or ""
            preview = misinfo.get("text_preview") or ""
        except (TypeError, ValueError):
            pass
        writer.writerow([
            a.id, s.id, s.username, _iso(s.scanned_at), _iso(a.resolved_at),
            s.trust_score, s.verdict, a.corrected_trust_score, s.corrected_verdict,
            a.module_at_fault, s.bot_percentage, s.engagement_score,
            category, preview, a.admin_note,
        ])

    # Exporting user-derived data is itself an auditable action.
    _log(db, admin, "feedback.export", "export", None, rows=len(rows))
    db.commit()

    filename = f"trustlens_feedback_{datetime.utcnow():%Y%m%d_%H%M}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ------------------------------------------------------------------------- #
# Audit log
# ------------------------------------------------------------------------- #
@router.get("/audit-log")
def audit_log(action: str = "all", page: int = 1, page_size: int = 50, db: Session = Depends(get_db)):
    page, page_size, offset = _page_args(page, page_size)
    q = db.query(AuditLog, User).outerjoin(User, User.id == AuditLog.admin_id)
    if action != "all":
        q = q.filter(AuditLog.action == action)

    total = q.count()
    rows = q.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size).all()
    actions = [r[0] for r in db.query(AuditLog.action).distinct().all()]

    return {
        "items": [
            {
                "id": log.id,
                "action": log.action,
                "admin": admin.full_name if admin else "Command line",
                "admin_email": admin.email if admin else None,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "details": json.loads(log.details) if log.details else None,
                "created_at": _iso(log.created_at),
            }
            for log, admin in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "actions": sorted(actions),
    }
