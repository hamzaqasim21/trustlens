# ============================================================
# TrustLens — PDF reports
# ============================================================
#
# Scope document:
#   §6.1  brands get "CSV or PDF export functionality"
#   §6.10 comparison results "can be exported as a PDF report"
#   §11   Layer 4: "a PDF report for brands"
#
# Built on the server with reportlab (a real PDF file, not a browser print of
# the page), from the SAME saved scan results the website shows. Nothing in a
# report is computed differently from the page: the numbers are read straight
# out of the stored result.

import io
import os
from datetime import datetime

import matplotlib
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

# DejaVu ships with matplotlib (already installed), and unlike the PDF
# built-in Helvetica it covers accented and non-English letters in names.
_FONT_DIR = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
pdfmetrics.registerFont(TTFont("TL", os.path.join(_FONT_DIR, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("TL-Bold", os.path.join(_FONT_DIR, "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFont(TTFont("TL-Mono", os.path.join(_FONT_DIR, "DejaVuSansMono.ttf")))

PLUM = colors.HexColor("#2B1140")
INK_SOFT = colors.HexColor("#6B5A7A")
LINE = colors.HexColor("#E4DDEA")
TINT = colors.HexColor("#FCEEF6")
PINK = colors.HexColor("#E1306C")
TONE = {  # deeper verdict steps that stay readable on white paper
    "Trusted": colors.HexColor("#07805F"),
    "Moderate Risk": colors.HexColor("#9A6206"),
    "High Risk": colors.HexColor("#C0321F"),
}

MODULE_LABEL = {
    "fake_follower": "Account authenticity",
    "engagement": "Engagement",
    "misinformation": "Misinformation",
    "credential": "Credentials",
}
MODULE_KIND = {
    "fake_follower": "Machine learning (Random Forest)",
    "engagement": "Rule-based",
    "misinformation": "Machine learning (XLM-RoBERTa) + rule-based red flags",
    "credential": "Rule-based + official doctor registers",
}
MODULE_ORDER = ["fake_follower", "engagement", "misinformation", "credential"]

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")


def _style(name, **kw):
    base = dict(fontName="TL", fontSize=9.5, leading=13.5, textColor=PLUM)
    base.update(kw)
    return ParagraphStyle(name, **base)


S = {
    "eyebrow": _style("eyebrow", fontName="TL-Mono", fontSize=8, textColor=INK_SOFT, leading=11),
    "h1": _style("h1", fontName="TL-Bold", fontSize=22, leading=26),
    "h2": _style("h2", fontName="TL-Bold", fontSize=13, leading=17, spaceBefore=10, spaceAfter=4),
    "body": _style("body"),
    "small": _style("small", fontSize=8, leading=11, textColor=INK_SOFT),
    "cell": _style("cell", fontSize=8.5, leading=11),
    "cellb": _style("cellb", fontName="TL-Bold", fontSize=8.5, leading=11),
    "center": _style("center", alignment=TA_CENTER),
}


_DRAWABLE = set(pdfmetrics.getFont("TL").face.charToGlyph)


def _esc(text):
    # Emoji and other characters the font has no shape for would print as
    # empty boxes, so they are left out of the PDF (the page shows them).
    text = "".join(ch for ch in str(text if text is not None else "")
                   if ord(ch) in _DRAWABLE or ch.isspace())
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _p(text, style="body"):
    return Paragraph(_esc(text), S[style])


def _fmt_int(n):
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "n/a"


def _score_of(result):
    """Corrected score when a reviewer upheld a report, else the original."""
    corr = result.get("correction") or {}
    if corr.get("trust_score") is not None:
        return corr["trust_score"], corr.get("verdict"), True
    ts = result.get("trust_score") or {}
    return ts.get("trust_score"), ts.get("verdict"), False


def misinfo_flag_count(result):
    return sum(1 for s in (result.get("misinformation_sources") or [])
               if s.get("status") == "success" and s.get("misinformation_flag"))


def engagement_rating(result):
    eng = result.get("engagement_analysis") or {}
    if eng.get("engagement_score") is None:
        return "Not measured"
    return f"{eng.get('status', '')} ({eng.get('engagement_rate')}% vs {eng.get('benchmark')}% normal)"


def credential_text(result):
    cred = result.get("credential_analysis") or {}
    if not cred.get("claims_found"):
        return "No claims"
    if cred.get("confidence_score") is None:
        return f"{', '.join(cred['claims_found'])}: not checkable"
    return f"{cred['confidence_score']}/100 ({', '.join(cred['claims_found'])})"


def summary_line(result):
    """The same facts the Results page's 'In one line' uses."""
    ff = result.get("fake_follower_analysis") or {}
    eng = result.get("engagement_analysis") or {}
    mi = result.get("misinformation_analysis") or {}
    parts = [f"the account itself is {round(100 - (ff.get('bot_percentage') or 0), 1)}% likely genuine"]
    if eng.get("engagement_score") is None:
        parts.append("engagement couldn't be measured")
    else:
        parts.append(f"engagement is {str(eng.get('status', '')).lower()} ({eng.get('engagement_rate')}%)")
    n = len([s for s in (result.get("misinformation_sources") or []) if s.get("status") == "success"])
    if mi.get("status") != "success":
        parts.append("no bio or caption text was available to check")
    elif mi.get("misinformation_flag"):
        parts.append(f"{misinfo_flag_count(result)} of {n} texts were flagged for misinformation")
    else:
        parts.append(f"no misinformation across {n} texts checked")
    return f"@{result.get('username')}: " + "; ".join(parts) + "."


# --------------------------------------------------------------------------- #
# Shared page furniture
# --------------------------------------------------------------------------- #
def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("TL", 7)
    canvas.setFillColor(INK_SOFT)
    w, _ = doc.pagesize
    canvas.drawString(doc.leftMargin, 10 * mm,
                      "TrustLens · automated analysis of public Instagram data. Scores are evidence, "
                      "not proof; read the breakdown before acting on them.")
    canvas.drawRightString(w - doc.rightMargin, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _doc(buf, title, pagesize=A4):
    return SimpleDocTemplate(buf, pagesize=pagesize, title=title, author="TrustLens",
                             leftMargin=16 * mm, rightMargin=16 * mm,
                             topMargin=14 * mm, bottomMargin=18 * mm)


def _table(rows, widths, header=True, zebra=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("FONT", (0, 0), (-1, -1), "TL", 8.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), PLUM),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        style += [("FONT", (0, 0), (-1, 0), "TL-Bold", 8),
                  ("TEXTCOLOR", (0, 0), (-1, 0), INK_SOFT),
                  ("LINEBELOW", (0, 0), (-1, 0), 0.8, PLUM)]
    if zebra:
        for r in range(1 if header else 0, len(rows), 2):
            style.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#FBF8FD")))
    t.setStyle(TableStyle(style))
    return t


# --------------------------------------------------------------------------- #
# 1. Single-scan report
# --------------------------------------------------------------------------- #
def scan_report_pdf(result: dict, scan_id=None, scanned_at=None) -> bytes:
    buf = io.BytesIO()
    doc = _doc(buf, f"TrustLens report @{result.get('username')}")
    score, verdict, corrected = _score_of(result)
    profile = result.get("raw_profile_data") or {}
    tone = TONE.get(verdict, PLUM)
    story = []

    when = scanned_at.strftime("%d %b %Y, %H:%M UTC") if isinstance(scanned_at, datetime) else "just now"
    story += [
        _p(f"TRUSTLENS · TRUST REPORT · SCAN #{scan_id if scan_id else '-'} · {when}", "eyebrow"),
        Spacer(1, 4),
        _p(f"{result.get('full_name') or result.get('username')}"
           f"{'  (verified)' if result.get('is_verified') else ''}", "h1"),
        _p(f"@{result.get('username')} · {_fmt_int(profile.get('followers'))} followers · "
           f"{_fmt_int(profile.get('posts'))} posts", "small"),
        Spacer(1, 10),
    ]

    score_box = Table([[
        Paragraph(f"<font name='TL-Bold' size='30'>{score}</font><br/>"
                  f"<font size='8' color='#6B5A7A'>TRUST SCORE / 100</font>", S["body"]),
        Paragraph(f"<font name='TL-Bold' size='15' color='{tone.hexval()}'>{_esc(verdict)}</font><br/>"
                  + ("<font size='8.5'>Corrected after review</font><br/>" if corrected else "")
                  + "<br/>"
                  f"{_esc(summary_line(result))}", S["body"]),
    ]], colWidths=[42 * mm, None])
    score_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TINT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LINEBEFORE", (0, 0), (0, -1), 3, tone),
    ]))
    story.append(score_box)

    # ---- Where the score came from ----
    ts = result.get("trust_score") or {}
    weights = ts.get("weights_used") or {}
    ms = ts.get("module_scores") or {}
    rows = [["Check", "Method", "Score", "Weight this scan"]]
    for m in MODULE_ORDER:
        if m in ms:
            rows.append([MODULE_LABEL[m], Paragraph(_esc(MODULE_KIND[m]), S["cell"]),
                         f"{ms[m]:.1f}", f"{weights.get(m, 0):g}%"])
        else:
            rows.append([MODULE_LABEL[m], Paragraph(_esc(MODULE_KIND[m]), S["cell"]),
                         "did not apply", "0% (redistributed)"])
    story += [_p("Where the score came from", "h2"),
              _table(rows, [38 * mm, 70 * mm, 24 * mm, 32 * mm]),
              _p("Weights re-normalise over the checks that applied, so they always add up to 100%. "
                 "A fake-account likelihood of 85% or more caps the score at 15.", "small")]

    # ---- Detail ----
    ff = result.get("fake_follower_analysis") or {}
    eng = result.get("engagement_analysis") or {}
    ca = result.get("comment_authenticity") or {}
    detail = [
        ["Fake-account likelihood", f"{ff.get('bot_percentage')}% ({ff.get('verdict', '')})"],
        ["Engagement", engagement_rating(result)],
        ["Posts analysed", str((result.get('engagement_data') or {}).get('posts_analyzed', 'n/a'))],
        ["Comment authenticity", str(ca.get("verdict", "n/a"))],
        ["Misinformation flags", f"{misinfo_flag_count(result)} flagged text(s)"],
        ["Credentials", credential_text(result)],
    ]
    story += [_p("Details", "h2"), _table(detail, [48 * mm, None], header=False)]

    srcs = [s for s in (result.get("misinformation_sources") or []) if s.get("status") == "success"]
    if srcs:
        rows = [["Text", "Where", "Result", "Risk"]]
        for s in sorted(srcs, key=lambda x: -(x.get("risk_score") or 0))[:14]:
            rows.append([Paragraph(_esc((s.get("text_preview") or "")[:90]), S["cell"]),
                         s.get("source", ""),
                         str(s.get("primary_category", "")).replace("_", " "),
                         str(s.get("risk_score", ""))])
        story += [KeepTogether([_p("Texts checked for misinformation", "h2"),
                                _table(rows, [96 * mm, 18 * mm, 40 * mm, 14 * mm])])]

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# 2. Comparison report
# --------------------------------------------------------------------------- #
def comparison_pdf(results: list) -> bytes:
    buf = io.BytesIO()
    doc = _doc(buf, "TrustLens comparison", pagesize=landscape(A4))
    names = [f"@{r.get('username')}" for r in results]
    story = [
        _p(f"TRUSTLENS · COMPARISON REPORT · {datetime.utcnow().strftime('%d %b %Y, %H:%M UTC')}", "eyebrow"),
        Spacer(1, 4),
        _p(" vs ".join(names), "h1"),
        Spacer(1, 6),
        _p(comparison_summary(results), "body"),
        Spacer(1, 8),
    ]

    header = ["Metric"] + names
    def row(label, fn):
        return [label] + [Paragraph(_esc(fn(r)), S["cell"]) for r in results]
    rows = [
        header,
        row("Trust Score", lambda r: f"{_score_of(r)[0]} / 100"),
        row("Verdict", lambda r: _score_of(r)[1]),
        row("Fake-account likelihood (bot %)", lambda r: f"{(r.get('fake_follower_analysis') or {}).get('bot_percentage')}%"),
        row("Misinformation flag count", lambda r: f"{misinfo_flag_count(r)} of "
            f"{len([s for s in (r.get('misinformation_sources') or []) if s.get('status') == 'success'])} texts"),
        row("Engagement authenticity", engagement_rating),
        row("Comment authenticity", lambda r: str((r.get("comment_authenticity") or {}).get("verdict", "n/a"))),
        row("Credential confidence", credential_text),
        row("Followers", lambda r: _fmt_int((r.get("raw_profile_data") or {}).get("followers"))),
    ]
    col = (doc.width - 55 * mm) / len(results)
    story.append(_table(rows, [55 * mm] + [col] * len(results)))
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def comparison_summary(results):
    scored = sorted(((_score_of(r)[0] or 0, r.get("username")) for r in results), reverse=True)
    best, runner = scored[0], scored[1]
    if best[0] - runner[0] < 5:
        return (f"The top accounts score within 5 points of each other ({best[0]} vs {runner[0]}); "
                f"none stands out clearly. Compare the rows below before deciding.")
    return (f"@{best[1]} scores highest ({best[0]}), {round(best[0] - runner[0], 1)} points ahead of "
            f"@{runner[1]} ({runner[0]}).")
