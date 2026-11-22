# ============================================================
# TrustLens — Creator tools (Web Dashboard, creator role)
# ============================================================
#
# Scope document §10, Creator / Influencer: "Connects their Instagram account
# via OAuth to receive a full audience authenticity report ... Can download a
# shareable Trust Badge certificate to share with brands, and receives tips
# for improving their credibility score."
#
# WHY A BIO CODE INSTEAD OF OAUTH (say this plainly if asked)
# -----------------------------------------------------------
# Instagram's official login for third-party apps (Meta's "Instagram API with
# Instagram Login") needs a Meta developer app that has passed Meta's App
# Review and business verification before any creator outside the developer
# team can use it; Phyllo, which the scope names, is a paid service. Neither is
# available to a student project. What OAuth is FOR here is proving the person
# owns the account, and that has a standard alternative used by many
# platforms: we give the creator a one-off code, they put it in their bio,
# and we read the bio back (through the same RapidAPI profile call every scan
# already uses). Only someone who can edit the account can do that.
#
# WHAT THE AUDIENCE REPORT IS, HONESTLY
# -------------------------------------
# Instagram blocks follower lists (see CLAUDE.md, "Followers-list endpoint is
# dead"), so no tool in this project can check followers one by one. The
# report is built from the audience signals we CAN read: how the audience
# engages (rate vs accounts of the same size, likes-to-comments), what the
# comments look like (diversity, bot-like repetition), and how steady
# engagement is post to post (sudden spikes are a classic sign of bought
# likes). It says that on the page.

import re
import secrets
import statistics
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db, User, CreatorClaim, ScanHistory, TrustBadge

router = APIRouter()

BADGE_VALID_DAYS = 30
BADGE_MAX_SCAN_AGE_DAYS = 7
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O/1/I to misread


def _code(n):
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(n))


def require_creator(user: User = Depends(get_current_user)) -> User:
    if (user.account_type or "personal") != "creator":
        raise HTTPException(403, "Creator tools are for creator accounts. Switch your account type in Settings.")
    return user


def _clean(username):
    return (username or "").strip().lstrip("@").lower()


def _verified_claim(db, user):
    return (db.query(CreatorClaim)
            .filter(CreatorClaim.user_id == user.id, CreatorClaim.status == "verified")
            .order_by(CreatorClaim.verified_at.desc()).first())


def _claim_payload(c):
    if not c:
        return None
    return {"username": c.username, "code": c.code, "status": c.status,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "verified_at": c.verified_at.isoformat() if c.verified_at else None}


# --------------------------------------------------------------------------- #
# Tips and the audience report — rule-based, from the scan's own numbers
# --------------------------------------------------------------------------- #
def engagement_consistency(posts):
    """How steady likes are across recent posts. Coefficient of variation
    (standard deviation / mean) plus any single post over 3x the median,
    which is what a bought-likes spike usually looks like."""
    likes = [p.get("likes") or 0 for p in (posts or [])]
    if len(likes) < 3 or not any(likes):
        return None
    mean = statistics.mean(likes)
    med = statistics.median(likes) or 1
    cv = statistics.pstdev(likes) / mean if mean else 0
    spikes = [i for i, v in enumerate(likes) if med and v > 3 * med]
    if cv < 0.6:
        label = "Steady"
    elif cv < 1.2:
        label = "Uneven"
    else:
        label = "Very uneven"
    return {"cv": round(cv, 2), "label": label, "posts": len(likes),
            "spike_posts": [(posts[i].get("code"), likes[i]) for i in spikes],
            "median_likes": med}


def audience_report(result):
    eng = result.get("engagement_analysis") or {}
    ca = result.get("comment_authenticity") or {}
    ff = result.get("fake_follower_analysis") or {}
    posts = (result.get("engagement_data") or {}).get("posts") or []
    cons = engagement_consistency(posts)

    signals = []
    if eng.get("engagement_score") is not None:
        signals.append({
            "label": "Engagement rate",
            "value": f"{eng.get('engagement_rate')}%",
            "detail": f"Accounts of your size ({eng.get('tier')}) usually get about {eng.get('benchmark')}%. "
                      f"Rated {str(eng.get('status', '')).lower()}.",
            "tone": {"green": "ok", "yellow": "warn", "red": "bad"}.get(eng.get("color"), "warn"),
        })
    if eng.get("comments_off"):
        signals.append({
            "label": "Likes per comment",
            "value": "Comments off",
            "detail": "Comments are turned off or restricted on your posts, so this check was skipped.",
            "tone": "warn",
        })
    elif eng.get("like_comment_ratio") is not None:
        r = eng["like_comment_ratio"]
        signals.append({
            "label": "Likes per comment",
            "value": f"{r:g}",
            "detail": ("A very high ratio can mean likes without real conversation."
                       if r > 200 else "Within the range real audiences usually show."),
            "tone": "warn" if r > 200 else "ok",
        })
    if ca.get("comment_diversity_score") is not None:
        signals.append({
            "label": "Comment authenticity",
            "value": f"{ca.get('comment_diversity_score'):g}% varied",
            "detail": str(ca.get("verdict", "")),
            "tone": "ok" if ((ca.get("comment_diversity_score") or 0) >= 40 or ca.get("campaign_keyword_detected")) else "warn",
        })
    if cons:
        detail = f"Likes vary by {cons['cv']}x of their average across {cons['posts']} posts."
        if cons["spike_posts"]:
            detail += f" {len(cons['spike_posts'])} post(s) got over 3x your usual likes."
        signals.append({"label": "Engagement consistency", "value": cons["label"], "detail": detail,
                        "tone": "ok" if cons["label"] == "Steady" else "warn"})
    signals.append({
        "label": "Account authenticity",
        "value": f"{round(100 - (ff.get('bot_percentage') or 0), 1)}%",
        "detail": "How genuine the account itself looks to the fake-account model.",
        "tone": "ok" if (ff.get("bot_percentage") or 0) < 40 else "bad",
    })
    return {
        "signals": signals,
        "consistency": cons,
        "limits": ("Instagram doesn't let any outside tool read an account's follower list, so this report "
                   "can't check followers one by one. It is built from how your audience actually engages."),
    }


def improvement_tips(result):
    """Plain, specific advice tied to what this scan actually found."""
    tips = []
    ff = result.get("fake_follower_analysis") or {}
    eng = result.get("engagement_analysis") or {}
    mi = result.get("misinformation_analysis") or {}
    cred = result.get("credential_analysis") or {}
    prof = result.get("raw_profile_data") or {}
    ca = result.get("comment_authenticity") or {}

    if (ff.get("bot_percentage") or 0) >= 40:
        missing = []
        if not prof.get("has_profile_pic"):
            missing.append("a profile photo")
        if not (prof.get("bio_length") or 0):
            missing.append("a bio")
        if (prof.get("posts") or 0) < 10:
            missing.append("more posts")
        tips.append({"area": "Account authenticity",
                     "tip": "Your profile looks like the fake accounts the model was trained on"
                            + (f" (it's missing {', '.join(missing)})" if missing else "")
                            + ". A complete, active profile is the biggest single fix."})
    if (prof.get("following") or 0) > 3 * max(prof.get("followers") or 0, 1):
        tips.append({"area": "Account authenticity",
                     "tip": "You follow far more accounts than follow you, a pattern typical of follow-for-follow "
                            "and bot accounts. Unfollowing inactive accounts helps."})
    if eng.get("engagement_score") is not None and eng.get("color") in ("yellow", "red"):
        tips.append({"area": "Engagement",
                     "tip": f"Your engagement ({eng.get('engagement_rate')}%) is below the "
                            f"{eng.get('benchmark')}% typical for {eng.get('tier')} accounts. Posting consistently "
                            "and replying to comments raises it; buying likes or followers lowers it over time."})
    if eng.get("engagement_score") is None:
        tips.append({"area": "Engagement",
                     "tip": "We couldn't read any posts. A public account with recent posts can be measured."})
    if mi.get("status") == "success" and mi.get("misinformation_flag"):
        flagged = [s for s in (result.get("misinformation_sources") or [])
                   if s.get("status") == "success" and s.get("misinformation_flag")]
        tips.append({"area": "Content",
                     "tip": f"{len(flagged)} of your texts were flagged ("
                            + ", ".join(sorted({str(s.get('primary_category', '')).replace('_', ' ') for s in flagged}))
                            + "). Check the breakdown for which ones; guaranteed-returns or cure claims are the "
                              "patterns that count most."})
    if cred.get("claims_found") and cred.get("confidence_score") is None:
        tips.append({"area": "Credentials",
                     "tip": "Your bio claims a qualification we can't check against a public register. "
                            "Linking to proof (a registration number or official profile) helps followers."})
    if (cred.get("verification") or {}).get("status") == "not_found":
        tips.append({"area": "Credentials",
                     "tip": "Your doctor claim didn't match the PMDC or US NPI register. Use your full name "
                            "exactly as registered, so it can be found."})
    if (ca.get("comment_diversity_score") is not None and ca["comment_diversity_score"] < 40
            and not ca.get("campaign_keyword_detected")):
        tips.append({"area": "Comments",
                     "tip": "Many comments look alike. Comment pods and bots do this; real conversation doesn't."})
    if not tips:
        tips.append({"area": "Overall",
                     "tip": "Nothing in this scan pulls your score down noticeably. Keep doing what you're doing, "
                            "and re-scan after big changes to your account."})
    return tips


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
def _latest_scan(db, user, username):
    return (db.query(ScanHistory)
            .filter(ScanHistory.user_id == user.id, ScanHistory.username == username)
            .order_by(ScanHistory.scanned_at.desc()).first())


def _badge_payload(b):
    now = datetime.utcnow()
    return {"code": b.code, "username": b.username, "trust_score": b.trust_score,
            "verdict": b.verdict,
            "issued_at": b.issued_at.isoformat(), "expires_at": b.expires_at.isoformat(),
            "revoked": bool(b.revoked), "expired": b.expires_at < now,
            "valid": (not b.revoked) and b.expires_at >= now}


@router.get("/creator")
def creator_home(user: User = Depends(require_creator), db: Session = Depends(get_db)):
    import json
    claim = _verified_claim(db, user)
    pending = (db.query(CreatorClaim)
               .filter(CreatorClaim.user_id == user.id, CreatorClaim.status == "pending")
               .order_by(CreatorClaim.created_at.desc()).first())
    out = {"claim": _claim_payload(claim), "pending": _claim_payload(pending),
           "scan": None, "audience": None, "tips": None, "badges": []}
    if claim:
        scan = _latest_scan(db, user, claim.username)
        if scan:
            result = json.loads(scan.raw_result)
            out["scan"] = {"id": scan.id, "scanned_at": scan.scanned_at.isoformat(),
                           "trust_score": scan.corrected_trust_score or scan.trust_score,
                           "verdict": scan.corrected_verdict or scan.verdict}
            out["audience"] = audience_report(result)
            out["tips"] = improvement_tips(result)
        badges = (db.query(TrustBadge).filter(TrustBadge.user_id == user.id)
                  .order_by(TrustBadge.issued_at.desc()).limit(10).all())
        out["badges"] = [_badge_payload(b) for b in badges]
    return out


@router.post("/creator/claim")
def start_claim(data: dict, user: User = Depends(require_creator), db: Session = Depends(get_db)):
    username = _clean(data.get("username"))
    if not re.fullmatch(r"[a-z0-9._]{1,30}", username):
        raise HTTPException(400, "Enter a valid Instagram username.")
    db.query(CreatorClaim).filter(CreatorClaim.user_id == user.id,
                                  CreatorClaim.status == "pending").delete()
    claim = CreatorClaim(user_id=user.id, username=username, code=f"TL-{_code(6)}")
    db.add(claim)
    db.commit()
    db.refresh(claim)
    return _claim_payload(claim)


@router.post("/creator/claim/verify")
def verify_claim(user: User = Depends(require_creator), db: Session = Depends(get_db)):
    from data_ingestion import fetch_instagram_profile, ProfileNotFoundError
    claim = (db.query(CreatorClaim)
             .filter(CreatorClaim.user_id == user.id, CreatorClaim.status == "pending")
             .order_by(CreatorClaim.created_at.desc()).first())
    if not claim:
        raise HTTPException(400, "Start by entering your Instagram username.")
    try:
        profile = fetch_instagram_profile(claim.username)
    except ProfileNotFoundError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Couldn't read the profile from Instagram just now: {e}")

    bio = (profile.get("biography") or "").upper()
    if claim.code.upper() not in bio:
        return {"verified": False,
                "message": f"We read @{claim.username}'s bio and didn't find {claim.code} yet. Save it in your "
                           "bio on Instagram, wait a few seconds, and try again."}

    # One owner per account: an older verified claim by anyone else is retired.
    db.query(CreatorClaim).filter(CreatorClaim.username == claim.username,
                                  CreatorClaim.status == "verified").update({"status": "superseded"})
    claim.status = "verified"
    claim.verified_at = datetime.utcnow()
    db.commit()
    return {"verified": True, "claim": _claim_payload(claim),
            "message": f"@{claim.username} is verified as yours. You can remove the code from your bio now."}


@router.post("/creator/scan")
def creator_scan(user: User = Depends(require_creator), db: Session = Depends(get_db)):
    from scan_service import run_scan, ScanFailed
    claim = _verified_claim(db, user)
    if not claim:
        raise HTTPException(400, "Verify your account first.")
    try:
        result = run_scan(db, user.id, claim.username, source="creator")
    except ScanFailed as e:
        return {"error": str(e), "kind": e.kind}
    return {"scan_id": result.get("scan_id")}


@router.post("/creator/badge")
def issue_badge(user: User = Depends(require_creator), db: Session = Depends(get_db)):
    claim = _verified_claim(db, user)
    if not claim:
        raise HTTPException(400, "Verify your account first.")
    scan = _latest_scan(db, user, claim.username)
    if not scan or scan.scanned_at < datetime.utcnow() - timedelta(days=BADGE_MAX_SCAN_AGE_DAYS):
        raise HTTPException(400, f"A badge needs a scan from the last {BADGE_MAX_SCAN_AGE_DAYS} days. "
                                 "Run a fresh scan first.")
    now = datetime.utcnow()
    badge = TrustBadge(code=_code(10), user_id=user.id, username=claim.username, scan_id=scan.id,
                       trust_score=scan.corrected_trust_score or scan.trust_score,
                       verdict=scan.corrected_verdict or scan.verdict,
                       issued_at=now, expires_at=now + timedelta(days=BADGE_VALID_DAYS))
    db.add(badge)
    db.commit()
    db.refresh(badge)
    return _badge_payload(badge)


@router.get("/creator/badge/{code}.pdf")
def badge_pdf(code: str, user: User = Depends(require_creator), db: Session = Depends(get_db)):
    from reports import badge_certificate_pdf
    badge = db.query(TrustBadge).filter(TrustBadge.code == code, TrustBadge.user_id == user.id).first()
    if not badge:
        raise HTTPException(404, "Badge not found.")
    return Response(badge_certificate_pdf(badge), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="trustlens_badge_{badge.username}.pdf"'})


@router.get("/badges/{code}")
def public_badge(code: str, db: Session = Depends(get_db)):
    """Public, no login: anyone handed a certificate can check it's real."""
    badge = db.query(TrustBadge).filter(TrustBadge.code == code.strip().upper()).first()
    if not badge:
        raise HTTPException(404, "No badge has this code. The certificate may not be genuine.")
    return _badge_payload(badge)
