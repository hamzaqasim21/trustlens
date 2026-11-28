# ============================================================
# TrustLens — Authentication
# ============================================================
#
# Our own email/password login, not a third-party provider. Passwords are
# hashed with bcrypt (industry standard — the original password is never
# stored, and can't be recovered from the hash). A successful login gets a
# signed JWT token; the frontend sends that token back on every request
# that needs to know who's logged in.

import os
import re
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session

from database import get_db, User

VERIFICATION_CODE_EXPIRES_MINUTES = 10


def generate_verification_code() -> str:
    """A random 6-digit code as a string, e.g. '048213'.

    Uses `secrets` (not `random`) — cryptographically strong, the correct
    choice for anything security-related, unlike Python's default PRNG."""
    return f"{secrets.randbelow(1_000_000):06d}"


def password_strength_error(password: str) -> str | None:
    """Returns a clear error message if the password is too weak, or None
    if it's acceptable. Baseline policy: 8+ characters, at least one letter
    AND one digit — catches things like "12345678" or "password" (all
    letters, or all digits) that pass a length-only check but are trivially
    weak. Not maximum-security-app strict (no special-character requirement)
    — appropriate for a student project login, not a bank."""
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if not re.search(r"[A-Za-z]", password):
        return "Password must include at least one letter"
    if not re.search(r"[0-9]", password):
        return "Password must include at least one number"
    return None


JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRES_HOURS = 24 * 7  # 7 days

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# bcrypt has a hard limit of 72 BYTES per password (not characters — a long
# password with multi-byte UTF-8 characters hits this sooner). Passing a
# longer password raises ValueError and crashes with a 500. Found this by
# deliberately testing a 500-character password against both /signup and
# /login — both crashed before this fix. main.py's signup validation
# rejects anything over this length with a clean message so no account can
# ever be created with a password bcrypt can't handle; verify_password
# below is also hardened independently, so login can never crash on this
# regardless of what's already in the database.
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Password too long for bcrypt (>72 bytes) — treat as simply wrong,
        # never crash. Same safe, generic outcome as any other bad password.
        return False


def create_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        # When the token was made. SQLite can give a deleted account's id to
        # the next new account, so without this an old token from the deleted
        # account would log straight into the new one (see _token_predates).
        "iat": int(now.timestamp()),
        "exp": now + timedelta(hours=TOKEN_EXPIRES_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> tuple[int, int | None]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload["user_id"], payload.get("iat")
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired, please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid session token")


def _token_predates(issued_at, user) -> bool:
    """True when the token can't belong to this account: it was made before
    the account existed (a deleted account's id handed to a new sign-up), or
    it is an older token from before issue times were recorded, which can't
    be checked and so isn't trusted. Either way: log in again."""
    if issued_at is None:
        return True
    created = user.created_at
    if created is None:
        return False
    # created_at is stored as naive UTC (datetime.utcnow); a whole-second
    # allowance covers iat being rounded down to the second.
    return issued_at + 1 < created.replace(tzinfo=timezone.utc).timestamp()


def get_current_user(
    authorization: str = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency: require a valid 'Authorization: Bearer <token>' header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Not logged in")

    token = authorization.removeprefix("Bearer ").strip()
    user_id, issued_at = _decode_token(token)

    user = db.query(User).filter(User.id == user_id).first()
    if not user or _token_predates(issued_at, user):
        raise HTTPException(401, "Session expired, please log in again")
    # Checked on every request, not only at login: a suspension has to take
    # effect immediately, even for someone holding a still-valid 7-day token.
    if user.is_active is False:
        raise HTTPException(403, "This account has been suspended")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """FastAPI dependency for every /admin route.

    This is the actual security boundary. The frontend also hides the Admin
    link from non-admins, but that is only presentation — anyone can type a
    URL or call the API directly, so the check that matters lives here on
    the server, where it cannot be bypassed from a browser.
    """
    if current_user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return current_user


def get_current_user_optional(
    authorization: str = Header(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    """Same as get_current_user, but returns None instead of raising when no
    one is logged in — for endpoints (like scanning) that work either way."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        user_id, issued_at = _decode_token(authorization.removeprefix("Bearer ").strip())
    except HTTPException:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    if user is not None and _token_predates(issued_at, user):
        return None
    # A suspended user can still use the public scanner like any visitor,
    # but the scan is not attached to their account.
    if user is not None and user.is_active is False:
        return None
    return user
