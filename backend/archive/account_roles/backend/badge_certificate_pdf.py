# Was the end of backend/reports.py. Needs reports.py's imports + QrCodeWidget
# (from reportlab.graphics.barcode.qr import QrCodeWidget) to run again.

# --------------------------------------------------------------------------- #
# 3. Trust Badge certificate
# --------------------------------------------------------------------------- #
def badge_certificate_pdf(badge) -> bytes:
    buf = io.BytesIO()
    w, h = landscape(A4)
    from reportlab.pdfgen import canvas as pdfcanvas
    c = pdfcanvas.Canvas(buf, pagesize=(w, h))
    c.setTitle(f"TrustLens Trust Badge @{badge.username}")
    tone = TONE.get(badge.verdict, PLUM)

    # Frame
    c.setFillColor(colors.white)
    c.rect(0, 0, w, h, fill=1, stroke=0)
    c.setStrokeColor(PLUM)
    c.setLineWidth(2)
    c.rect(14 * mm, 14 * mm, w - 28 * mm, h - 28 * mm)
    c.setStrokeColor(PINK)
    c.setLineWidth(0.6)
    c.rect(17 * mm, 17 * mm, w - 34 * mm, h - 34 * mm)

    c.setFillColor(INK_SOFT)
    c.setFont("TL-Mono", 10)
    c.drawCentredString(w / 2, h - 36 * mm, "TRUSTLENS · TRUST BADGE CERTIFICATE")
    c.setFillColor(PLUM)
    c.setFont("TL-Bold", 34)
    c.drawCentredString(w / 2, h - 56 * mm, f"@{badge.username}")
    c.setFont("TL", 11)
    c.setFillColor(INK_SOFT)
    c.drawCentredString(w / 2, h - 65 * mm,
                        "This Instagram account was verified as belonging to its holder and scanned by TrustLens.")

    # Score
    c.setFillColor(tone)
    c.setFont("TL-Bold", 64)
    c.drawCentredString(w / 2, h - 98 * mm, f"{badge.trust_score:g}")
    c.setFont("TL-Bold", 16)
    c.drawCentredString(w / 2, h - 109 * mm, f"{badge.verdict}  ·  Trust Score out of 100")
    c.setFillColor(PLUM)
    c.setFont("TL", 10)
    conf = f"Confidence {badge.confidence}%" if badge.confidence is not None else "Confidence not recorded"
    c.drawCentredString(w / 2, h - 118 * mm,
                        f"{conf}  ·  Issued {badge.issued_at:%d %b %Y}  ·  Valid until {badge.expires_at:%d %b %Y}")

    # Verification
    url = f"{FRONTEND_URL}/badge/{badge.code}"
    qr = QrCodeWidget(url)
    b = qr.getBounds()
    size = 30 * mm
    d = Drawing(size, size, transform=[size / (b[2] - b[0]), 0, 0, size / (b[3] - b[1]), 0, 0])
    d.add(qr)
    from reportlab.graphics import renderPDF
    renderPDF.draw(d, c, 26 * mm, 24 * mm)
    c.setFont("TL-Mono", 9)
    c.setFillColor(PLUM)
    c.drawString(62 * mm, 44 * mm, f"Badge code: {badge.code}")
    c.drawString(62 * mm, 38 * mm, f"Check it is genuine: {url}")
    c.setFont("TL", 8)
    c.setFillColor(INK_SOFT)
    c.drawString(62 * mm, 31 * mm, "The page at that address shows the real record. If it disagrees with this "
                                   "certificate, trust the page.")
    c.drawRightString(w - 26 * mm, 24 * mm,
                      "Automated analysis of public data; a score is evidence, not a guarantee.")
    c.showPage()
    c.save()
    return buf.getvalue()
