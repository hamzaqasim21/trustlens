# ============================================================
# TrustLens — Visual analytics data, exports and PDF reports
# ============================================================
#
# Endpoints the Results, Comparison, Dashboard and Brand pages use:
#   GET  /accounts/{username}/timeline  follower-growth timeline (Visual Analytics)
#   POST /scans/{id}/explain            plain-language chart summary (LLM, rule fallback)
#   GET  /reports/scan/{id}.pdf         one scan as a PDF report
#   POST /reports/compare.pdf           a comparison as a PDF report
#   GET  /exports/scans.csv             your scans as CSV (brand export)

import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db, User, ScanHistory
from score_confidence import assess_confidence

router = APIRouter()

# A change of 10%+ in followers between two scans of the same account is
# flagged on the growth timeline. Organic growth is gradual; bought followers
# and mass purges show up as jumps.
FOLLOWER_JUMP = 0.10


def load_result(scan: ScanHistory) -> dict:
    try:
        result = json.loads(scan.raw_result)
    except (TypeError, ValueError):
        raise HTTPException(410, "This scan's full result wasn't saved. Run it again.")
    result["scan_id"] = scan.id
    result["scanned_at"] = scan.scanned_at.isoformat() if scan.scanned_at else None
    result["correction"] = ({"trust_score": scan.corrected_trust_score, "verdict": scan.corrected_verdict}
                            if scan.corrected_trust_score is not None else None)
    if "confidence" not in result:           # scans saved before confidence existed
        result["confidence"] = assess_confidence(result)
    return result


def _own_scan(db, user, scan_id):
    scan = db.get(ScanHistory, scan_id)
    if not scan or (scan.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Scan not found")
    return scan


# --------------------------------------------------------------------------- #
# Follower growth timeline
# --------------------------------------------------------------------------- #
@router.get("/accounts/{username}/timeline")
def follower_timeline(username: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Every time TrustLens has scanned this account (by anyone), as numbers
    only — never who scanned it. Instagram gives no follower history to
    outside tools, so this history is TrustLens's own: it grows as the
    account is scanned over time."""
    username = username.strip().lstrip("@").lower()
    scans = (db.query(ScanHistory.scanned_at, ScanHistory.followers, ScanHistory.trust_score,
                      ScanHistory.corrected_trust_score)
             .filter(ScanHistory.username == username, ScanHistory.followers != None)  # noqa: E711
             .order_by(ScanHistory.scanned_at.asc()).all())

    # Several scans on the same day collapse to that day's last one, so a
    # demo that scans the same account five times doesn't draw five dots.
    by_day = {}
    for s in scans:
        by_day[s.scanned_at.date().isoformat()] = s
    points, anomalies = [], []
    prev = None
    for day, s in by_day.items():
        point = {"date": day, "followers": s.followers,
                 "trust_score": s.corrected_trust_score if s.corrected_trust_score is not None else s.trust_score}
        if prev and prev["followers"]:
            change = (s.followers - prev["followers"]) / prev["followers"]
            point["change_pct"] = round(change * 100, 2)
            if abs(change) >= FOLLOWER_JUMP:
                point["anomaly"] = True
                anomalies.append({"date": day, "change_pct": round(change * 100, 1),
                                  "from": prev["followers"], "to": s.followers})
        points.append(point)
        prev = point
    return {"username": username, "points": points, "anomalies": anomalies,
            "jump_threshold_pct": int(FOLLOWER_JUMP * 100),
            "note": ("Built from TrustLens's own scans of this account over time; Instagram doesn't share "
                     "follower history with outside tools.")}


# --------------------------------------------------------------------------- #
# Chart summary (LLM explainer)
# --------------------------------------------------------------------------- #
_explain_cache = {}


@router.post("/scans/{scan_id}/explain")
def explain_scan(scan_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from chart_explainer import explain_charts
    scan = _own_scan(db, user, scan_id)
    if scan_id not in _explain_cache:
        timeline = follower_timeline(scan.username, user, db)
        _explain_cache[scan_id] = explain_charts(load_result(scan), timeline)
    return _explain_cache[scan_id]


# --------------------------------------------------------------------------- #
# PDF reports
# --------------------------------------------------------------------------- #
def _pdf(data, filename):
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/reports/scan/{scan_id}.pdf")
def scan_pdf(scan_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from reports import scan_report_pdf
    scan = _own_scan(db, user, scan_id)
    result = load_result(scan)
    return _pdf(scan_report_pdf(result, scan.id, scan.scanned_at), f"trustlens_{scan.username}_{scan.id}.pdf")


@router.post("/reports/compare.pdf")
def compare_pdf(data: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from reports import comparison_pdf
    ids = data.get("scan_ids") or []
    if not isinstance(ids, list) or not 2 <= len(ids) <= 4:
        raise HTTPException(400, "A comparison report needs 2 to 4 scans.")
    results = [load_result(_own_scan(db, user, int(i))) for i in ids]
    name = "_vs_".join(r["username"] for r in results)[:120]
    return _pdf(comparison_pdf(results), f"trustlens_compare_{name}.pdf")


# --------------------------------------------------------------------------- #
# CSV export
# --------------------------------------------------------------------------- #
CSV_COLUMNS = [
    "scan_id", "scanned_at", "username", "full_name", "followers", "trust_score", "verdict",
    "requires_review", "confidence_pct", "confidence_label", "fake_account_likelihood_pct",
    "engagement_rate_pct", "engagement_benchmark_pct", "engagement_status",
    "misinformation_flag_count", "texts_checked", "comment_authenticity",
    "credential_claims", "credential_confidence", "corrected_trust_score", "source",
]


def csv_row(scan, result):
    eng = result.get("engagement_analysis") or {}
    conf = result.get("confidence") or {}
    cred = result.get("credential_analysis") or {}
    srcs = [s for s in (result.get("misinformation_sources") or []) if s.get("status") == "success"]
    return {
        "scan_id": scan.id,
        "scanned_at": scan.scanned_at.isoformat() if scan.scanned_at else "",
        "username": scan.username,
        "full_name": scan.full_name or "",
        "followers": scan.followers,
        "trust_score": scan.trust_score,
        "verdict": scan.verdict,
        "requires_review": conf.get("needs_review"),
        "confidence_pct": conf.get("confidence"),
        "confidence_label": conf.get("label"),
        "fake_account_likelihood_pct": scan.bot_percentage,
        "engagement_rate_pct": eng.get("engagement_rate") if eng.get("engagement_score") is not None else "",
        "engagement_benchmark_pct": eng.get("benchmark"),
        "engagement_status": eng.get("status"),
        "misinformation_flag_count": sum(1 for s in srcs if s.get("misinformation_flag")),
        "texts_checked": len(srcs),
        "comment_authenticity": (result.get("comment_authenticity") or {}).get("verdict", ""),
        "credential_claims": "; ".join(cred.get("claims_found") or []),
        "credential_confidence": cred.get("confidence_score") if cred.get("confidence_score") is not None else "",
        "corrected_trust_score": scan.corrected_trust_score if scan.corrected_trust_score is not None else "",
        "source": scan.source or "web",
    }


@router.get("/exports/scans.csv")
def export_csv(ids: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(ScanHistory).filter(ScanHistory.user_id == user.id)
    if ids.strip():
        try:
            wanted = [int(x) for x in ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(400, "ids must be a comma-separated list of scan numbers.")
        q = q.filter(ScanHistory.id.in_(wanted))
    scans = q.order_by(ScanHistory.scanned_at.desc()).limit(1000).all()

    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=CSV_COLUMNS)
    w.writeheader()
    for s in scans:
        try:
            result = load_result(s)
        except HTTPException:
            result = {}
        w.writerow(csv_row(s, result))
    # A byte-order mark so Excel opens names with accents/Urdu correctly.
    return Response("﻿" + out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="trustlens_scans.csv"'})
