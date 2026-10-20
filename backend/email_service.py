# ============================================================
# TrustLens — Email Service (account verification codes)
# ============================================================
#
# Sends real email through Gmail's SMTP server using a Gmail "App Password"
# — not the Google Cloud Console / Custom Search API path that caused
# billing trouble earlier in this project. This is a personal Gmail account
# setting (2-Step Verification → App Passwords), completely free, no
# billing account involved at all.
#
# If GMAIL_ADDRESS / GMAIL_APP_PASSWORD aren't set in .env yet, sending
# fails loudly with a clear message rather than pretending to succeed —
# consistent with this project's "never fake it" rule.

import os
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")


def email_configured() -> bool:
    return bool(GMAIL_ADDRESS and GMAIL_APP_PASSWORD)


def send_verification_code(to_email: str, code: str) -> None:
    """Sends a one-time verification code by email — used at signup, and
    again at login if an account was never verified. Raises on failure —
    the caller decides how to surface that, this never silently pretends
    to work."""
    if not email_configured():
        raise RuntimeError(
            "Email isn't configured yet — set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in backend/.env"
        )

    subject = f"Your TrustLens verification code: {code}"
    body = (
        f"Your TrustLens verification code is:\n\n"
        f"    {code}\n\n"
        f"This code expires in 10 minutes. If you didn't try to sign up or log in, "
        f"you can safely ignore this email."
    )

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to_email

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
        server.starttls()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, [to_email], msg.as_string())


def send_email(to_email: str, subject: str, body: str) -> None:
    """Plain-text email through the same Gmail sender. Raises on failure."""
    if not email_configured():
        raise RuntimeError("Email isn't configured (GMAIL_ADDRESS / GMAIL_APP_PASSWORD).")
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to_email
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
        server.starttls()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, [to_email], msg.as_string())
