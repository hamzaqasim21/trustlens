# ============================================================
# TrustLens — Engagement Analyzer Module
# ============================================================

def analyze_engagement(followers, likes_avg, comments_avg, posts):

    # ---- Engagement Rate Calculation ----
    total_interactions = likes_avg + comments_avg
    engagement_rate = (total_interactions / (followers + 1)) * 100
    engagement_rate = round(engagement_rate, 2)

    # ---- Benchmark Based on Follower Range ----
    if followers < 10000:
        benchmark = 5.0
        tier = "Nano"
    elif followers < 100000:
        benchmark = 3.0
        tier = "Micro"
    elif followers < 1000000:
        benchmark = 1.5
        tier = "Macro"
    else:
        benchmark = 0.8
        tier = "Mega"

    # ---- Like to Comment Ratio ----
    like_comment_ratio = likes_avg / (comments_avg + 1)

    # ---- Engagement Score 0-100 ----
    if engagement_rate >= benchmark * 1.5:
        engagement_score = 90
        status = "Excellent"
        color = "green"
    elif engagement_rate >= benchmark:
        engagement_score = 75
        status = "Healthy"
        color = "green"
    elif engagement_rate >= benchmark * 0.5:
        engagement_score = 50
        status = "Below Average"
        color = "yellow"
    else:
        engagement_score = 20
        status = "Suspicious"
        color = "red"

    # ---- Suspicious Pattern Detection ----
    flags = []

    if like_comment_ratio > 500:
        flags.append("Extremely low comments relative to likes")

    if engagement_rate == 0 and followers > 1000:
        flags.append("Zero engagement despite large following")

    if posts == 0:
        flags.append("No posts found")

    if followers > 100000 and comments_avg < 5:
        flags.append("Large account with almost no comments")

    return {
        "engagement_rate":    engagement_rate,
        "benchmark":          benchmark,
        "tier":               tier,
        "status":             status,
        "color":              color,
        "engagement_score":   engagement_score,
        "like_comment_ratio": round(like_comment_ratio, 2),
        "flags":              flags,
        "total_flags":        len(flags)
    }

from collections import Counter

def analyze_comment_authenticity(comments: list) -> dict:
    """
    Analyzes comment text for genuine diversity vs bot-like patterns.
    Recognizes 'campaign keyword' patterns (many different users posting
    the same short word, e.g. 'link') as a legitimate engagement tactic,
    not a fraud signal.
    """
    if not comments:
        return {
            "comment_diversity_score": None,
            "campaign_keyword_detected": False,
            "verdict": "No comments available to analyze"
        }

    total = len(comments)
    short_comments = [c for c in comments if len(c.split()) <= 3]
    long_comments = [c for c in comments if len(c.split()) > 3]

    short_ratio = len(short_comments) / total

    # ---- Detect campaign keyword pattern ----
    campaign_keyword_detected = False
    if short_comments:
        short_counter = Counter(c.lower().strip() for c in short_comments)
        most_common_text, most_common_count = short_counter.most_common(1)[0]
        # If one short phrase makes up a large chunk of short comments,
        # and short comments are a meaningful share of all comments,
        # treat it as a legitimate campaign, not bot spam.
        if most_common_count >= 3 and (most_common_count / len(short_comments)) > 0.3:
            campaign_keyword_detected = True

    # ---- Measure genuine diversity in the longer, non-keyword comments ----
    if long_comments:
        unique_long = len(set(c.lower().strip() for c in long_comments))
        diversity_score = round((unique_long / len(long_comments)) * 100, 1)
    else:
        diversity_score = None

    # ---- Verdict ----
    if campaign_keyword_detected:
        verdict = "Campaign keyword pattern detected — likely a legitimate call-to-action, not bot activity"
    elif diversity_score is not None and diversity_score < 40:
        verdict = "Low comment diversity — possible bot/comment-pod activity"
    elif diversity_score is not None:
        verdict = "Comments show healthy diversity — likely genuine engagement"
    else:
        verdict = "Not enough data to determine authenticity"

    return {
        "total_comments_analyzed": total,
        "short_comment_ratio": round(short_ratio * 100, 1),
        "campaign_keyword_detected": campaign_keyword_detected,
        "comment_diversity_score": diversity_score,
        "verdict": verdict
    }