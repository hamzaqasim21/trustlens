# ============================================================
# TrustLens — Database Setup
# ============================================================
#
# Uses SQLite by default: one file (trustlens.db) next to this script,
# no server or install needed. Set DATABASE_URL in .env to point at
# PostgreSQL instead — nothing else in this file would need to change.

import os
from datetime import datetime

from sqlalchemy import (
    create_engine, inspect, text,
    Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey,
)
from sqlalchemy.orm import sessionmaker, declarative_base

# Absolute path, so the server always opens THIS file whichever folder it was
# started from. A relative "./trustlens.db" would quietly create a new, empty
# database somewhere else, and every account would seem to have vanished.
_DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trustlens.db")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///" + _DEFAULT_DB.replace("\\", "/"))

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    email_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # "user" or "admin". There is deliberately no endpoint that lets anyone
    # make themselves an admin — the first admin is created from the command
    # line (make_admin.py), and after that only an existing admin can grant it.
    role = Column(String, default="user")
    # False = suspended by an admin. Suspended accounts cannot log in and any
    # token they already hold stops working on its next request.
    is_active = Column(Boolean, default=True)
    last_login_at = Column(DateTime, nullable=True)
    # Scope §10 user types: "personal" (normal user), "creator" (influencer)
    # or "brand" (brand / agency). Chosen at signup, changeable in Settings.
    # Separate from `role` on purpose: admin is a permission, this is what
    # kind of dashboard the person gets.
    account_type = Column(String, default="personal")


class VerificationCode(Base):
    """A one-time email verification code. Sent once at signup (proves the
    email is real and reachable) and can be resent at login if an account
    was never verified. Stored in the DB (not memory) so it survives a
    server restart/reload — this backend reloads often during development."""
    __tablename__ = "verification_codes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    code = Column(String)           # 6-digit numeric code, as a string
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    used = Column(Boolean, default=False)


class ScanHistory(Base):
    __tablename__ = "scan_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    username = Column(String, index=True)
    full_name = Column(String, nullable=True)
    is_verified = Column(Boolean, default=False)

    followers = Column(Integer, nullable=True)
    trust_score = Column(Float)
    verdict = Column(String)
    color = Column(String)

    bot_percentage = Column(Float, nullable=True)
    engagement_score = Column(Float, nullable=True)
    misinformation_flag = Column(Boolean, nullable=True)
    deepfake_band = Column(String, nullable=True)       # real | fake | uncertain | not_applicable | error
    deepfake_image_risk = Column(Integer, nullable=True)

    raw_result = Column(Text)  # full /analyze-live JSON response, for the Results page to reuse
    scanned_at = Column(DateTime, default=datetime.utcnow)

    # Set only when an admin upholds a dispute. The original score above is
    # never overwritten, so there is always a record of what the models said
    # versus what a human decided — that difference is the retraining signal.
    corrected_trust_score = Column(Float, nullable=True)
    corrected_verdict = Column(String, nullable=True)

    # Where the scan came from: "web" (someone pressed Scan), "watchlist"
    # (an automatic re-check of a watched account), "bulk" (a brand's bulk
    # analysis), "api" (a brand's API key) or "creator" (Creator studio).
    source = Column(String, default="web")


class Appeal(Base):
    """A user disputing a score. Scope document §7: "an appeal mechanism
    allows submission of evidence for admin review within 48 hours. Corrected
    scores feed back into model retraining." """
    __tablename__ = "appeals"

    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(Integer, ForeignKey("scan_history.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)

    reason = Column(Text)
    evidence_url = Column(String, nullable=True)

    status = Column(String, default="pending", index=True)   # pending | upheld | rejected
    created_at = Column(DateTime, default=datetime.utcnow)

    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    admin_note = Column(Text, nullable=True)
    corrected_trust_score = Column(Float, nullable=True)
    # Which part of the pipeline the admin judged to be wrong. This is what
    # makes an upheld dispute useful for retraining rather than just a
    # changed number: it says which model the case should go back to.
    module_at_fault = Column(String, nullable=True)


class AuditLog(Base):
    """Every admin action, recorded. Scope document lists audit logs among
    the things the database holds; this is also simply how a real admin
    panel stays accountable — a suspension or a changed score always has a
    who, a when and a why attached."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String, index=True)          # e.g. "user.suspend", "appeal.resolve"
    target_type = Column(String, nullable=True)  # "user" | "appeal" | "export"
    target_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)        # JSON
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class WatchedAccount(Base):
    """An account a user asked to keep an eye on. Scope §10, normal users:
    "Can save accounts for ongoing monitoring and receive alerts when scores
    drop." last_score is what the newest check said; an Alert is raised when
    a later check comes in lower."""
    __tablename__ = "watched_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    username = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    baseline_score = Column(Float, nullable=True)     # the score when it was first watched
    last_score = Column(Float, nullable=True)
    last_verdict = Column(String, nullable=True)
    last_scan_id = Column(Integer, ForeignKey("scan_history.id"), nullable=True)
    last_checked_at = Column(DateTime, nullable=True)
    last_error = Column(String, nullable=True)


class Alert(Base):
    """A watched account's score dropped. Shown on the Dashboard, and emailed
    when the Gmail sender is configured."""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    username = Column(String)
    old_score = Column(Float)
    new_score = Column(Float)
    old_verdict = Column(String, nullable=True)
    new_verdict = Column(String, nullable=True)
    scan_id = Column(Integer, ForeignKey("scan_history.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    read = Column(Boolean, default=False)
    emailed = Column(Boolean, default=False)


class ApiKey(Base):
    """A brand account's API key. Only the SHA-256 hash is stored; the key
    itself is shown once, when it is made, and can never be read back."""
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    name = Column(String)
    prefix = Column(String)          # first characters, so the owner can tell keys apart
    key_hash = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    revoked = Column(Boolean, default=False)


class CreatorClaim(Base):
    """A creator proving they own an Instagram account by putting a one-off
    code in its bio. pending -> verified (or superseded when someone else
    later proves ownership of the same account)."""
    __tablename__ = "creator_claims"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    username = Column(String, index=True)
    code = Column(String)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    verified_at = Column(DateTime, nullable=True)


class TrustBadge(Base):
    """A Trust Badge certificate a creator can hand to brands. The public
    page /badge/<code> shows this record, so a brand can check it's real."""
    __tablename__ = "trust_badges"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    username = Column(String)
    scan_id = Column(Integer, ForeignKey("scan_history.id"))
    trust_score = Column(Float)
    verdict = Column(String)
    # Left over from the confidence feature (set aside 2026-09-29). Kept so the
    # existing table still matches; new badges leave it empty.
    confidence = Column(Integer, nullable=True)
    issued_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    revoked = Column(Boolean, default=False)


def delete_user_and_data(db, user):
    """Permanently removes an account and every row tied to it. Used by
    Settings -> Delete account (DELETE /me) and delete_user.py, so the two can
    never disagree about what "everything" means. Does not commit."""
    scan_ids = [s.id for s in db.query(ScanHistory.id).filter(ScanHistory.user_id == user.id).all()]
    db.query(Appeal).filter(Appeal.user_id == user.id).delete(synchronize_session=False)
    if scan_ids:
        db.query(Appeal).filter(Appeal.scan_id.in_(scan_ids)).delete(synchronize_session=False)
        db.query(Alert).filter(Alert.scan_id.in_(scan_ids)).delete(synchronize_session=False)
    for model in (Alert, WatchedAccount, ApiKey, CreatorClaim, TrustBadge, VerificationCode):
        db.query(model).filter(model.user_id == user.id).delete(synchronize_session=False)
    db.query(ScanHistory).filter(ScanHistory.user_id == user.id).delete(synchronize_session=False)
    db.delete(user)


# Columns added to tables that already exist on people's machines.
# create_all() only creates *missing tables*; it never alters an existing one,
# so without this an existing trustlens.db would crash on the first query
# that touches a new column. ADD COLUMN is non-destructive — existing rows
# keep every value they had and simply get the default for the new column.
_ADDED_COLUMNS = {
    "users": {
        "role": "VARCHAR DEFAULT 'user'",
        "is_active": "BOOLEAN DEFAULT TRUE",
        "last_login_at": "TIMESTAMP",
        "account_type": "VARCHAR DEFAULT 'personal'",
    },
    "scan_history": {
        "corrected_trust_score": "FLOAT",
        "corrected_verdict": "VARCHAR",
        "source": "VARCHAR DEFAULT 'web'",
    },
}


def _add_missing_columns():
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if not inspector.has_table(table):
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


# --------------------------------------------------------------------------- #
# Automatic backups
# --------------------------------------------------------------------------- #
# Every time the backend starts, a dated copy of the database is saved to
# backend/backups/ (gitignored — it holds real emails and password hashes),
# keeping the newest BACKUPS_KEPT. Set TRUSTLENS_BACKUP_DIR in backend/.env to
# ALSO copy it somewhere off this disk (a USB drive, or a Google Drive / OneDrive
# folder that syncs to the cloud), so losing the laptop doesn't lose the data.
# Uses SQLite's own backup command, which makes a consistent copy even if the
# database is being written to at that moment (a plain file copy might not).
BACKUPS_KEPT = 14
_BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")


def backup_database():
    if not DATABASE_URL.startswith("sqlite:///"):
        return []          # a real database server has its own backup tooling
    import sqlite3
    src_path = DATABASE_URL[len("sqlite:///"):]
    if not os.path.exists(src_path) or os.path.getsize(src_path) == 0:
        return []
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    made = []
    for folder in [_BACKUP_DIR, os.getenv("TRUSTLENS_BACKUP_DIR", "").strip()]:
        if not folder:
            continue
        try:
            os.makedirs(folder, exist_ok=True)
            dest = os.path.join(folder, f"trustlens_{stamp}.db")
            src, dst = sqlite3.connect(src_path), sqlite3.connect(dest)
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
            made.append(dest)
            old = sorted(f for f in os.listdir(folder) if f.startswith("trustlens_") and f.endswith(".db"))
            for f in old[:-BACKUPS_KEPT]:
                os.remove(os.path.join(folder, f))
        except Exception as e:   # a failed backup must never stop the site starting
            print(f"[TrustLens] Database backup to {folder} failed: {e}")
    return made


def init_db():
    if not os.getenv("TRUSTLENS_DISABLE_BACKGROUND"):   # not during tests
        backup_database()
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
