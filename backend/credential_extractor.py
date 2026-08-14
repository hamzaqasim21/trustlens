# ============================================================
# TrustLens — Credential Extractor Module
# Extracts professional credential claims from bio text
# ============================================================

import re
import os
import requests
from dotenv import load_dotenv

load_dotenv()

GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
GOOGLE_SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

# Known credential patterns — expand this list as needed
CREDENTIAL_PATTERNS = {
    "MBBS": r"\bMBBS\b",
    "MD": r"\bM\.?D\.?\b",
    "PhD": r"\bPh\.?D\.?\b",
    "CFA": r"\bCFA\b",
    "CPA": r"\bCPA\b",
    "Certified Financial Planner": r"\bCertified Financial Planner\b|\bCFP\b",
    "Registered Dietitian": r"\bRegistered Dietitian\b|\bRD\b",
    "Licensed Therapist": r"\bLicensed Therapist\b|\bLPC\b|\bLCSW\b",
    "Esq (Lawyer)": r"\bEsq\.?\b|\bAttorney at Law\b",
    "Professor": r"\bProf\.?\b|\bProfessor\b",
    "Doctor": r"\bDr\.?\b",
    "Nutritionist": r"\bNutritionist\b",
    "Certified Personal Trainer": r"\bCertified Personal Trainer\b|\bCPT\b",
}


def extract_credential_claims(bio_text: str) -> list:
    """
    Scans bio text for known professional credential patterns.
    Returns a list of matched credential claims.
    """
    if not bio_text:
        return []

    found_claims = []
    for credential_name, pattern in CREDENTIAL_PATTERNS.items():
        if re.search(pattern, bio_text, re.IGNORECASE):
            found_claims.append(credential_name)

    return found_claims

def calculate_credential_confidence(bio_text: str, is_verified: bool = False) -> dict:
    """
    Extracts claims and produces a Credential Confidence Score.
    Note: full Google/LinkedIn verification is a separate step —
    this gives an initial confidence estimate based on claim presence
    and account verification status.
    """
    claims = extract_credential_claims(bio_text)

    if not claims:
        return {
            "claims_found": [],
            "confidence_score": None,
            "verdict": "No credential claims detected in bio"
        }

    base_score = 60 if is_verified else 35

    specific_claims = [c for c in claims if c not in ("Doctor", "Professor")]
    specificity_bonus = min(len(specific_claims) * 10, 30)

    confidence_score = min(base_score + specificity_bonus, 95)

    if confidence_score >= 70:
        verdict = "Moderately credible — verified account with specific credential claims"
    elif confidence_score >= 45:
        verdict = "Low-moderate confidence — claims present but unverified externally"
    else:
        verdict = "Low confidence — unverified account making credential claims"

    return {
        "claims_found": claims,
        "confidence_score": confidence_score,
        "verdict": verdict
    }

def search_credential_verification(full_name: str, credential: str) -> dict:
    """
    Searches LinkedIn/professional registries for a matching credential record.
    Returns whether a plausible match was found.
    """
    if not GOOGLE_SEARCH_API_KEY or not GOOGLE_SEARCH_ENGINE_ID:
        return {"found": False, "reason": "Search not configured"}

    query = f'"{full_name}" {credential}'
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_SEARCH_API_KEY,
        "cx": GOOGLE_SEARCH_ENGINE_ID,
        "q": query,
        "num": 3
    }

    try:
        response = requests.get(url, params=params)
        data = response.json()

        items = data.get("items", [])
        if items:
            return {
                "found": True,
                "match_count": len(items),
                "top_result_title": items[0].get("title", ""),
                "top_result_link": items[0].get("link", "")
            }
        else:
            return {"found": False, "match_count": 0}
    except Exception as e:
        return {"found": False, "reason": str(e)}