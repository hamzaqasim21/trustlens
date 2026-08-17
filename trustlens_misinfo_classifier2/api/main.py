"""
main.py
-------
TrustLens Misinformation Classifier — FastAPI service.

Endpoints:
    GET  /health              -> quick check that the service + model are up
    POST /classify             -> classify a single piece of text (caption/transcript)
    POST /classify-profile     -> fetch recent Instagram posts for a username
                                   and classify each caption (uses your teammate's
                                   RapidAPI key via .env)

Run locally:
    uvicorn main:app --reload --port 8000

Then open frontend/index.html in a browser (it points at localhost:8000).
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from model_loader import classify_text
from instagram_fetch import fetch_latest_post, fetch_post_by_shortcode, fetch_recent_captions
from url_parser import parse_instagram_input

app = FastAPI(title="TrustLens Misinformation Classifier")

# Wide-open CORS for local testing with the plain-HTML frontend.
# Tighten this to your actual frontend origin before deploying.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ClassifyRequest(BaseModel):
    text: str


class UrlRequest(BaseModel):
    url: str


class ProfileRequest(BaseModel):
    username: str
    amount: int = 12


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/classify")
def classify(req: ClassifyRequest):
    result = classify_text(req.text)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


@app.post("/classify-url")
def classify_url(req: UrlRequest):
    """
    Single entry point for testing against real content: paste a
    profile URL, a post/reel URL, or just a bare username, and get
    back the classification for one real post.
    """
    parsed = parse_instagram_input(req.url)

    if parsed["type"] == "invalid":
        raise HTTPException(
            status_code=400,
            detail="Couldn't recognize that as an Instagram profile URL, "
                   "post/reel URL, or username.",
        )

    try:
        if parsed["type"] == "post":
            post = fetch_post_by_shortcode(req.url, parsed["media_type"])
        else:  # profile
            post = fetch_latest_post(parsed["value"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    if not post["caption"].strip():
        raise HTTPException(
            status_code=422,
            detail="Fetched the post but couldn't extract caption text. "
                   "Run with DEBUG=1 in .env and check the raw API response "
                   "to fix the field mapping in instagram_fetch.py.",
        )

    classification = classify_text(post["caption"])
    return {
        "input_url": req.url,
        "resolved_type": parsed["type"],
        "resolved_value": parsed["value"],
        "post_id": post["post_id"],
        "caption": post["caption"],
        "like_count": post["like_count"],
        "comment_count": post["comment_count"],
        "classification": classification,
    }


@app.post("/classify-profile")
def classify_profile(req: ProfileRequest):
    try:
        posts = fetch_recent_captions(req.username, req.amount)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Instagram fetch failed: {e}")

    results = []
    for post in posts:
        if not post["caption"].strip():
            continue
        classification = classify_text(post["caption"])
        results.append({
            "post_id": post["post_id"],
            "caption": post["caption"],
            "like_count": post["like_count"],
            "comment_count": post["comment_count"],
            "classification": classification,
        })

    if not results:
        return {
            "username": req.username,
            "posts_analyzed": 0,
            "warning": "No captions extracted — check instagram_fetch.py "
                       "field mapping against the raw API response (run with DEBUG=1).",
            "results": [],
        }

    avg_risk = round(sum(r["classification"]["risk_score"] for r in results) / len(results))
    flagged = [r for r in results if r["classification"]["misinformation_flag"]]

    return {
        "username": req.username,
        "posts_analyzed": len(results),
        "posts_flagged": len(flagged),
        "average_risk_score": avg_risk,
        "results": results,
    }