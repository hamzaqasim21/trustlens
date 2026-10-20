# ============================================================
# TrustLens — Watchlist and score-drop alerts (Web Dashboard, normal users)
# ============================================================
#
# Scope document §10, Normal Social Media User: "Can save accounts for
# ongoing monitoring and receive alerts when scores drop."
#
# How it works:
#   - A user watches an account. Its current score becomes the baseline.
#   - Every time that user's scan of the account finishes (a manual scan, a
#     "Re-check" press, or the automatic daily re-check below), record_scan()
#     compares the new score with the last one.
#   - If it dropped by DROP_POINTS or more, or fell into a worse verdict band,
#     an Alert is created. It shows on the Dashboard and, when the Gmail
#     sender is configured, is emailed too.
#
# The automatic re-check is a background thread in the backend process. It
# re-scans at most a few watched accounts per round and only ones not checked
# in the last WATCHLIST_RECHECK_HOURS (default 24), so it can never flood the
# RapidAPI quota or slow a live demo. WATCHLIST_RECHECK_HOURS=0 turns it off.

import os
import threading
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user
from database import SessionLocal, get_db, User, WatchedAccount, Alert, ScanHistory
from trust_score import verdict_for

router = APIRouter()

DROP_POINTS = 5            # a fall of 5+ points is an alert
MAX_WATCHED = 25           # per user, keeps the automatic re-check bounded
RECHECK_HOURS = float(os.getenv("WATCHLIST_RECHECK_HOURS", "24"))
RECHECK_PER_ROUND = 3
ROUND_EVERY_SECONDS = 30 * 60
FIRST_ROUND_AFTER_SECONDS = 10 * 60   # never during the first minutes after start-up

_TIER = {"High Risk": 0, "Moderate Risk": 1, "Trusted": 2}


def _clean(username):
    return (username or "").strip().lstrip("@").lower()


def _effective(scan):
    """A reviewer's corrected score, when there is one, is the real one."""
    if scan.corrected_trust_score is not None:
        return scan.corrected_trust_score, scan.corrected_verdict
    return scan.trust_score, scan.verdict


def is_drop(old_score, old_verdict, new_score, new_verdict):
    if old_score is None or new_score is None:
        return False
    if old_score - new_score >= DROP_POINTS:
        return True
    return _TIER.get(new_verdict, 1) < _TIER.get(old_verdict, 1)


def _email_alert(user_email, alert_id, username, old, new, old_v, new_v):
    """Runs in its own thread so a slow mail server never slows a scan."""
    if os.getenv("TRUSTLENS_DISABLE_EMAIL"):
        return
    try:
        from email_service import email_configured, send_email
        if not email_configured():
            return
        send_email(
            user_email,
            f"TrustLens alert: @{username}'s Trust Score dropped to {new}",
            f"An account you're watching on TrustLens has dropped.\n\n"
            f"  @{username}\n  {old} ({old_v})  ->  {new} ({new_v})\n\n"
            f"Open your TrustLens dashboard to see what changed.\n"
            f"You're getting this because you added @{username} to your watchlist.",
        )
        db = SessionLocal()
        try:
            a = db.get(Alert, alert_id)
            if a:
                a.emailed = True
                db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"Warning: alert email failed: {e}")


def record_scan(db, user_id, scan):
    """Called after every saved scan. Updates this user's watch entry for the
    account (if they watch it) and raises an alert on a drop."""
    if not user_id:
        return None
    entry = (db.query(WatchedAccount)
             .filter(WatchedAccount.user_id == user_id,
                     WatchedAccount.username == _clean(scan.username))
             .first())
    if not entry:
        return None

    new_score, new_verdict = _effective(scan)
    alert = None
    if is_drop(entry.last_score, entry.last_verdict, new_score, new_verdict):
        alert = Alert(user_id=user_id, username=entry.username,
                      old_score=entry.last_score, new_score=new_score,
                      old_verdict=entry.last_verdict, new_verdict=new_verdict,
                      scan_id=scan.id)
        db.add(alert)
    entry.last_score = new_score
    entry.last_verdict = new_verdict
    entry.last_scan_id = scan.id
    entry.last_checked_at = datetime.utcnow()
    entry.last_error = None
    if entry.baseline_score is None:
        entry.baseline_score = new_score
    db.commit()

    if alert:
        user = db.get(User, user_id)
        if user:
            threading.Thread(target=_email_alert, daemon=True, args=(
                user.email, alert.id, entry.username, entry_score_text(alert.old_score),
                entry_score_text(new_score), alert.old_verdict, new_verdict)).start()
    return alert


def entry_score_text(v):
    return "n/a" if v is None else f"{v:g}"


def _entry_payload(e):
    return {
        "id": e.id,
        "username": e.username,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "baseline_score": e.baseline_score,
        "last_score": e.last_score,
        "last_verdict": e.last_verdict,
        "last_scan_id": e.last_scan_id,
        "last_checked_at": e.last_checked_at.isoformat() if e.last_checked_at else None,
        "last_error": e.last_error,
        "change": (round(e.last_score - e.baseline_score, 1)
                   if e.last_score is not None and e.baseline_score is not None else None),
    }


def _alert_payload(a):
    return {
        "id": a.id, "username": a.username,
        "old_score": a.old_score, "new_score": a.new_score,
        "old_verdict": a.old_verdict, "new_verdict": a.new_verdict,
        "scan_id": a.scan_id, "read": a.read, "emailed": a.emailed,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.get("/watchlist")
def list_watchlist(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(WatchedAccount).filter(WatchedAccount.user_id == user.id)
            .order_by(WatchedAccount.created_at.desc()).all())
    return {"items": [_entry_payload(e) for e in rows],
            "auto_recheck_hours": RECHECK_HOURS or None,
            "drop_points": DROP_POINTS}


@router.post("/watchlist")
def add_to_watchlist(data: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    username = _clean(data.get("username"))
    if not username or len(username) > 30:
        raise HTTPException(400, "Enter a valid Instagram username.")
    existing = (db.query(WatchedAccount)
                .filter(WatchedAccount.user_id == user.id, WatchedAccount.username == username).first())
    if existing:
        return _entry_payload(existing)
    if db.query(WatchedAccount).filter(WatchedAccount.user_id == user.id).count() >= MAX_WATCHED:
        raise HTTPException(400, f"You can watch up to {MAX_WATCHED} accounts. Remove one first.")

    entry = WatchedAccount(user_id=user.id, username=username)
    # Start from the user's own latest scan of it, if there is one, so
    # watching an account you just scanned costs no extra Instagram request.
    latest = (db.query(ScanHistory)
              .filter(ScanHistory.user_id == user.id, ScanHistory.username == username)
              .order_by(ScanHistory.scanned_at.desc()).first())
    if latest:
        score, verdict = _effective(latest)
        entry.baseline_score = entry.last_score = score
        entry.last_verdict = verdict
        entry.last_scan_id = latest.id
        entry.last_checked_at = latest.scanned_at
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _entry_payload(entry)


def _own_entry(db, user, entry_id):
    entry = db.get(WatchedAccount, entry_id)
    if not entry or entry.user_id != user.id:
        raise HTTPException(404, "Not on your watchlist.")
    return entry


@router.delete("/watchlist/{entry_id}")
def remove_from_watchlist(entry_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    entry = _own_entry(db, user, entry_id)
    db.delete(entry)
    db.commit()
    return {"ok": True}


@router.post("/watchlist/{entry_id}/recheck")
def recheck(entry_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Run a real scan now. Same pipeline as the Scan page."""
    from scan_service import run_scan, ScanFailed
    entry = _own_entry(db, user, entry_id)
    try:
        result = run_scan(db, user.id, entry.username, source="watchlist")
    except ScanFailed as e:
        entry.last_error = str(e)[:300]
        entry.last_checked_at = datetime.utcnow()
        db.commit()
        return {"error": str(e), "kind": e.kind, "entry": _entry_payload(entry)}
    db.refresh(entry)
    return {"entry": _entry_payload(entry), "scan_id": result.get("scan_id")}


@router.get("/alerts")
def list_alerts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(Alert).filter(Alert.user_id == user.id)
            .order_by(Alert.created_at.desc()).limit(50).all())
    return {"items": [_alert_payload(a) for a in rows],
            "unread": sum(1 for a in rows if not a.read)}


@router.post("/alerts/read")
def mark_alerts_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Alert).filter(Alert.user_id == user.id, Alert.read == False).update({"read": True})  # noqa: E712
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Automatic daily re-check
# --------------------------------------------------------------------------- #
def _due_entries(db, now):
    cutoff = now - timedelta(hours=RECHECK_HOURS)
    return (db.query(WatchedAccount)
            .join(User, User.id == WatchedAccount.user_id)
            .filter(User.is_active == True)  # noqa: E712
            .filter((WatchedAccount.last_checked_at == None) | (WatchedAccount.last_checked_at < cutoff))  # noqa: E711
            .order_by(WatchedAccount.last_checked_at.asc().nullsfirst())
            .limit(RECHECK_PER_ROUND).all())


def recheck_round():
    """One round of the background re-check. Returns how many were checked."""
    from scan_service import run_scan, ScanFailed
    db = SessionLocal()
    checked = 0
    try:
        for entry in _due_entries(db, datetime.utcnow()):
            try:
                run_scan(db, entry.user_id, entry.username, source="watchlist")
            except ScanFailed as e:
                entry.last_error = str(e)[:300]
                entry.last_checked_at = datetime.utcnow()
                db.commit()
            except Exception as e:
                db.rollback()
                print(f"Warning: watchlist re-check of @{entry.username} failed: {e}")
            checked += 1
    finally:
        db.close()
    return checked


def start_background_rechecks():
    if RECHECK_HOURS <= 0 or os.getenv("TRUSTLENS_DISABLE_BACKGROUND"):
        return

    def loop():
        time.sleep(FIRST_ROUND_AFTER_SECONDS)
        while True:
            try:
                recheck_round()
            except Exception as e:
                print(f"Warning: watchlist re-check round failed: {e}")
            time.sleep(ROUND_EVERY_SECONDS)

    threading.Thread(target=loop, daemon=True, name="watchlist-recheck").start()
