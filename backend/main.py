# ============================================================
# TrustLens — Main FastAPI Backend
# ============================================================

import sys
import os
import json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
sys.path.append(os.path.join(os.path.dirname(__file__), "misinfo_classifier", "api"))
from model_loader import classify_text

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from fake_follower import analyze_fake_followers
from engagement_analyzer import analyze_engagement
from trust_score import calculate_trust_score
from database import init_db, get_db, ScanHistory, User, VerificationCode, Appeal
from scan_service import run_scan, ScanFailed
import watchlist
import insights
from auth import (
    hash_password, verify_password, create_token, get_current_user,
    EMAIL_RE, MAX_PASSWORD_BYTES, password_strength_error,
    generate_verification_code, VERIFICATION_CODE_EXPIRES_MINUTES,
)
from email_service import send_verification_code, email_configured
from admin import router as admin_router, APPEAL_SLA_HOURS

@asynccontextmanager
async def lifespan(app):
    # Load the 1.1 GB misinformation model in the background as the server
    # starts, instead of making the first scan (or the first reel the browser
    # extension checks) wait for it. The server answers requests meanwhile.
    import threading
    from model_loader import load_model
    threading.Thread(target=load_model, daemon=True).start()
    # Daily automatic re-check of watched accounts (watchlist.py).
    watchlist.start_background_rechecks()
    yield


app = FastAPI(
    title="TrustLens API",
    description="AI-Powered Influencer Authenticity Detection",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    # Lets the frontend read the admin CSV export's filename; browsers hide
    # every non-basic response header from cross-origin JavaScript otherwise.
    expose_headers=["Content-Disposition"],
)

init_db()

# ---- The browser extension's two model services, served from this process ----
# The extension used to run them as two extra programs (ports 8001 and 8002),
# each loading its OWN copy of the same models the website already has in
# memory: two copies of the 1.1 GB misinformation model whenever both were
# running. Measured on a friend's 8 GB laptop, that ran Windows out of memory
# and the misinformation service was killed mid-demo. Mounted here, the
# extension uses the very same loaded model objects as the website — one copy,
# and the website and the extension literally cannot disagree. The standalone
# versions still work on their own (used by the tests).
_GATEWAY_DIR = os.path.join(os.path.dirname(__file__), "browser_extension", "gateway")
if _GATEWAY_DIR not in sys.path:
    sys.path.append(_GATEWAY_DIR)
try:
    import post_checker_api as _ext_classifier
    import follower_api as _ext_account
    app.mount("/ext/classifier", _ext_classifier.app)
    app.mount("/ext/account", _ext_account.app)
except Exception as _exc:  # the website itself must still start
    print(f"[TrustLens] Browser-extension model services not mounted: {_exc}")

app.include_router(admin_router)
app.include_router(watchlist.router)
app.include_router(insights.router)



def _user_payload(user: User) -> dict:
    """What the frontend is told about the logged-in user. `role` is how it
    knows to show the Admin link — purely cosmetic; every admin endpoint
    re-checks the role on the server regardless."""
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role or "user",
    }


@app.get("/")
def home():
    return {
        "message": "TrustLens API is running",
        "version": "1.0.0",
        "status": "active"
    }

@app.post("/analyze")
def analyze_profile(data: dict):
    username        = data.get("username", "unknown")
    followers       = data.get("followers", 0)
    following       = data.get("following", 0)
    posts           = data.get("posts", 0)
    likes_avg       = data.get("likes_avg", 0)
    comments_avg    = data.get("comments_avg", 0)
    has_profile_pic = data.get("has_profile_pic", 1)
    bio_length      = data.get("bio_length", 0)
    has_external_url= data.get("has_external_url", 0)
    is_private      = data.get("is_private", 0)

    fake_result = analyze_fake_followers(
        followers, following, posts,
        has_profile_pic, bio_length, has_external_url, is_private
    )

    engagement_result = analyze_engagement(
        followers, likes_avg, comments_avg, posts
    )

    trust_result = calculate_trust_score(
        fake_result["bot_percentage"],
        engagement_result["engagement_score"]
    )

    return {
        "username": username,
        "fake_follower_analysis": fake_result,
        "engagement_analysis": engagement_result,
        "trust_score": trust_result
    }

@app.post("/analyze-live")
def analyze_profile_live(
    data: dict,
    db: Session = Depends(get_db),
    # Login required (changed 2026-09-26). A scan used to run for anyone and
    # was only tied to an account if a token happened to be sent — which is
    # why logged-out scans never showed on the Dashboard and couldn't be
    # disputed. The product flow is now "sign up / log in, then scan", and
    # this is the check that actually enforces it; the frontend redirect is
    # only presentation and can be skipped by calling the API directly.
    current_user: User = Depends(get_current_user),
):
    try:
        return run_scan(db, current_user.id, data.get("username"), source="web")
    except ScanFailed as e:
        # "kind" lets the frontend tell "this username doesn't exist, check the
        # spelling" apart from "Instagram was slow, try again".
        return {"error": str(e), "kind": e.kind}


@app.post("/test-misinfo")
def test_misinfo(data: dict):
    text = data.get("text", "")
    return classify_text(text)


def _send_verification_code(db: Session, user: User) -> None:
    """Shared by /signup and /login: generates a code, saves it, emails it.
    Raises HTTPException on failure so callers don't need to repeat that."""
    if not email_configured():
        raise HTTPException(
            503,
            "Email verification isn't fully set up yet — the app's Gmail sender "
            "(GMAIL_ADDRESS / GMAIL_APP_PASSWORD) hasn't been configured in backend/.env."
        )

    code = generate_verification_code()
    db.add(VerificationCode(
        user_id=user.id,
        code=code,
        expires_at=datetime.utcnow() + timedelta(minutes=VERIFICATION_CODE_EXPIRES_MINUTES),
    ))
    db.commit()

    try:
        send_verification_code(user.email, code)
    except Exception as e:
        raise HTTPException(500, f"Could not send the verification email: {e}")


@app.post("/signup")
def signup(data: dict, db: Session = Depends(get_db)):
    """Creates the account, then emails a one-time code to prove the email
    is real. No token yet — /verify-email finishes the job. This is what
    catches a made-up/nonexistent email at signup: the code can never
    arrive, so the account can never be verified or used."""
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not full_name:
        raise HTTPException(400, "Please enter your name")
    if len(full_name) > 100:
        raise HTTPException(400, "Name is too long")
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Please enter a valid email address")
    if len(email) > 254:  # RFC 5321 max email length
        raise HTTPException(400, "Email address is too long")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise HTTPException(400, f"Password must be {MAX_PASSWORD_BYTES} characters or fewer")
    strength_error = password_strength_error(password)
    if strength_error:
        raise HTTPException(400, strength_error)

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(400, "An account with this email already exists")

    user = User(full_name=full_name, email=email, password_hash=hash_password(password), email_verified=False)
    db.add(user)
    db.commit()
    db.refresh(user)

    _send_verification_code(db, user)

    return {
        "requires_verification": True,
        "email": user.email,
        "message": f"We emailed a 6-digit code to {user.email} to confirm it's real. It expires in {VERIFICATION_CODE_EXPIRES_MINUTES} minutes.",
    }


@app.post("/login")
def login(data: dict, db: Session = Depends(get_db)):
    """Password-only login — no code required once the email has already
    been verified once (that's the whole point of doing it at signup
    instead of every login). If an account somehow never got verified
    (e.g. the user closed the tab during signup), this resends a fresh
    code instead of leaving them stuck."""
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")

    # Only revealed after the password is proven correct, so this can't be
    # used to probe which emails belong to suspended accounts.
    if user.is_active is False:
        raise HTTPException(403, "This account has been suspended. Contact the TrustLens team if you think this is a mistake.")

    if not user.email_verified:
        _send_verification_code(db, user)
        return {
            "requires_verification": True,
            "email": user.email,
            "message": f"This account was never verified. We emailed a new 6-digit code to {user.email}.",
        }

    user.last_login_at = datetime.utcnow()
    db.commit()

    token = create_token(user.id)
    return {"token": token, "user": _user_payload(user)}


@app.post("/verify-email")
def verify_email(data: dict, db: Session = Depends(get_db)):
    """Checks the emailed code. On success, marks the account verified
    (permanently — future logins never need a code again) and logs the
    user in immediately, same response shape /login uses."""
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()

    user = db.query(User).filter(User.email == email).first()
    # Same "don't leak which part was wrong" principle as password login.
    generic_error = HTTPException(401, "Incorrect or expired code")
    if not user:
        raise generic_error

    verification_code = (
        db.query(VerificationCode)
        .filter(VerificationCode.user_id == user.id, VerificationCode.code == code, VerificationCode.used == False)
        .order_by(VerificationCode.created_at.desc())
        .first()
    )
    if not verification_code or verification_code.expires_at < datetime.utcnow():
        raise generic_error

    if user.is_active is False:
        raise HTTPException(403, "This account has been suspended. Contact the TrustLens team if you think this is a mistake.")

    verification_code.used = True
    user.email_verified = True
    user.last_login_at = datetime.utcnow()
    db.commit()

    token = create_token(user.id)
    return {"token": token, "user": _user_payload(user)}


@app.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return _user_payload(current_user)


@app.get("/scans")
def get_scan_history(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Real scan history for the Dashboard page — only this user's own scans, most recent first."""
    scans = (
        db.query(ScanHistory)
        .filter(ScanHistory.user_id == current_user.id)
        .order_by(ScanHistory.scanned_at.desc())
        .limit(limit)
        .all()
    )

    appeal_status = {
        a.scan_id: a.status
        for a in db.query(Appeal).filter(Appeal.scan_id.in_([s.id for s in scans])).all()
    } if scans else {}

    return [
        {
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
            "appeal_status": appeal_status.get(s.id),
            "source": s.source or "web",
            "scanned_at": s.scanned_at.isoformat() if s.scanned_at else None,
        }
        for s in scans
    ]


@app.get("/scans/{scan_id}")
def get_saved_result(
    scan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reopens a past scan's full result exactly as it was saved, so the
    Dashboard can link back to the Results page without re-running the scan
    (which would spend RapidAPI quota and might give a different answer if
    the account has changed since). Only your own scans."""
    scan = db.query(ScanHistory).filter(ScanHistory.id == scan_id).first()
    # 404 rather than 403 for someone else's scan: don't confirm it exists.
    if not scan or scan.user_id != current_user.id:
        raise HTTPException(404, "Scan not found")
    try:
        result = json.loads(scan.raw_result)
    except (TypeError, ValueError):
        raise HTTPException(410, "This scan's full result wasn't saved, so it can't be reopened. Run it again.")

    appeal = db.query(Appeal).filter(Appeal.scan_id == scan.id).first()
    result["scan_id"] = scan.id
    result["scan_owned"] = True
    result["scanned_at"] = scan.scanned_at.isoformat() if scan.scanned_at else None
    # The original score stays exactly what the models said; a correction
    # from an upheld dispute is reported alongside it, never written over it.
    result["correction"] = (
        {"trust_score": scan.corrected_trust_score, "verdict": scan.corrected_verdict}
        if scan.corrected_trust_score is not None else None
    )
    result["appeal_status"] = appeal.status if appeal else None
    return result


# ------------------------------------------------------------------------- #
# Account settings — real changes, not decorative buttons.
# ------------------------------------------------------------------------- #
@app.patch("/me")
def update_me(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change your display name. Email is deliberately not editable here:
    changing it would need the new address verified all over again, and a
    half-built version of that would let anyone attach an unverified email."""
    full_name = (data.get("full_name") or "").strip()
    if not full_name:
        raise HTTPException(400, "Please enter your name")
    if len(full_name) > 100:
        raise HTTPException(400, "Name is too long")
    current_user.full_name = full_name
    db.commit()
    return _user_payload(current_user)


@app.post("/me/password")
def change_password(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_password = data.get("current_password") or ""
    new_password = data.get("new_password") or ""

    if not verify_password(current_password, current_user.password_hash):
        raise HTTPException(400, "Your current password is incorrect")
    if len(new_password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise HTTPException(400, f"Password must be {MAX_PASSWORD_BYTES} characters or fewer")
    strength_error = password_strength_error(new_password)
    if strength_error:
        raise HTTPException(400, strength_error)
    if new_password == current_password:
        raise HTTPException(400, "The new password must be different from the current one")

    current_user.password_hash = hash_password(new_password)
    db.commit()
    return {"message": "Password updated."}


@app.delete("/me")
def delete_me(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Permanently deletes the account and everything tied to it: scans,
    disputes, verification codes. Asks for the password again so a stolen
    session token alone can't wipe an account."""
    if not verify_password(data.get("password") or "", current_user.password_hash):
        raise HTTPException(400, "Password is incorrect")
    # Same no-self-lockout rule the admin console uses: an admin account is
    # tied to the audit trail and dispute decisions, so another admin has to
    # remove the admin role first.
    if current_user.role == "admin":
        raise HTTPException(400, "Admin accounts can't be deleted from here. Ask another admin to remove your admin role first.")

    scan_ids = [s.id for s in db.query(ScanHistory.id).filter(ScanHistory.user_id == current_user.id).all()]
    db.query(Appeal).filter(Appeal.user_id == current_user.id).delete(synchronize_session=False)
    if scan_ids:
        db.query(Appeal).filter(Appeal.scan_id.in_(scan_ids)).delete(synchronize_session=False)
    db.query(ScanHistory).filter(ScanHistory.user_id == current_user.id).delete(synchronize_session=False)
    db.query(VerificationCode).filter(VerificationCode.user_id == current_user.id).delete(synchronize_session=False)
    db.delete(current_user)
    db.commit()
    return {"message": "Your account and scan history have been deleted."}


# ------------------------------------------------------------------------- #
# Score disputes — the user side of the appeal mechanism.
# The admin side (review, uphold/reject) lives in admin.py.
# ------------------------------------------------------------------------- #
APPEAL_REASON_MIN = 20
APPEAL_REASON_MAX = 2000


@app.post("/appeals")
def create_appeal(
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dispute a score. One dispute per scan, and only on a scan that
    belongs to you — otherwise anyone could flood the admin queue with
    disputes about scans they never ran."""
    scan_id = data.get("scan_id")
    reason = (data.get("reason") or "").strip()
    evidence_url = (data.get("evidence_url") or "").strip() or None

    scan = db.query(ScanHistory).filter(ScanHistory.id == scan_id).first()
    # 404 rather than 403 for someone else's scan: don't confirm it exists.
    if not scan or scan.user_id != current_user.id:
        raise HTTPException(404, "That scan isn't on your account. Scans run while logged out can't be disputed — log in and scan again.")

    if len(reason) < APPEAL_REASON_MIN:
        raise HTTPException(400, f"Please explain why the score is wrong in at least {APPEAL_REASON_MIN} characters, so a reviewer has something to go on.")
    if len(reason) > APPEAL_REASON_MAX:
        raise HTTPException(400, f"Please keep the explanation under {APPEAL_REASON_MAX} characters.")
    if evidence_url and (not evidence_url.startswith(("http://", "https://")) or len(evidence_url) > 500):
        raise HTTPException(400, "Evidence must be a link starting with http:// or https://")

    if db.query(Appeal).filter(Appeal.scan_id == scan.id).first():
        raise HTTPException(409, "This score has already been disputed.")

    appeal = Appeal(scan_id=scan.id, user_id=current_user.id, reason=reason, evidence_url=evidence_url)
    db.add(appeal)
    db.commit()
    db.refresh(appeal)

    return {
        "id": appeal.id,
        "status": appeal.status,
        "message": f"Dispute submitted. A reviewer will look at it within {APPEAL_SLA_HOURS} hours.",
    }


@app.get("/appeals/mine")
def my_appeals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(Appeal, ScanHistory)
        .join(ScanHistory, ScanHistory.id == Appeal.scan_id)
        .filter(Appeal.user_id == current_user.id)
        .order_by(Appeal.created_at.desc())
        .all()
    )
    return [
        {
            "id": a.id,
            "scan_id": s.id,
            "username": s.username,
            "original_score": s.trust_score,
            "original_verdict": s.verdict,
            "status": a.status,
            "reason": a.reason,
            "admin_note": a.admin_note,
            "corrected_trust_score": a.corrected_trust_score,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        }
        for a, s in rows
    ]