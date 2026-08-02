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