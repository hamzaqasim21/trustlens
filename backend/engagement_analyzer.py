# ============================================================
# TrustLens — Engagement Analyzer Module
# ============================================================

# Engagement score as a smooth curve of (rate / benchmark), instead of the old
# 4-step staircase (20 / 50 / 75 / 90). With steps, a Macro account at 0.74%
# scored 20 and at 0.75% scored 50 — a 0.01% difference moving the final
# Trust Score by ~8 points. The curve passes through the old step values at
# the MIDDLE of each old band (ratio 0.25 -> 20, 0.75 -> 50, 1.25 -> 75,
# 2.0 -> 90), so scores don't shift on average; only the cliffs are gone.
_CURVE = [(0.0, 5), (0.5, 35), (1.0, 65), (1.5, 85), (2.5, 95)]


def _smooth_score(ratio):
    if ratio >= _CURVE[-1][0]:
        return float(_CURVE[-1][1])
    for (x0, y0), (x1, y1) in zip(_CURVE, _CURVE[1:]):
        if ratio <= x1:
            return y0 + (y1 - y0) * (ratio - x0) / (x1 - x0)
    return float(_CURVE[-1][1])


def analyze_engagement(followers, likes_avg, comments_avg, posts, posts_analyzed=None, comments_off=False):

    # ---- No posts came back: nothing was measured ----
    # Instagram sometimes returns no posts (a network hiccup, rate limiting,
    # a private account). That used to average to 0 likes and be scored
    # "Suspicious" — a real scan of a healthy 22%-engagement account was
    # dragged to Moderate Risk this way. Missing data is reported as missing,
    # and the Trust Score leaves this module out, same as Misinformation
    # when there is no text.
    if posts_analyzed == 0:
        return {
            "engagement_rate": None,
            "benchmark": None,
            "tier": None,
            "status": "Not measured",
            "color": "gray",
            "engagement_score": None,
            "like_comment_ratio": None,
            "flags": ["No posts could be read for this account, so engagement wasn't measured"],
            "total_flags": 1,
            "measured": False,
        }

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
    # Not computed when the creator has turned comments off: zero comments is
    # then a privacy setting, and a huge likes-per-comment ratio would read as
    # a bot signal that isn't there (found on a real scan, @raisa.creationz).
    like_comment_ratio = None if comments_off else likes_avg / (comments_avg + 1)

    # ---- Engagement Score 0-100 (smooth) + a readable band ----
    ratio = engagement_rate / benchmark
    engagement_score = round(_smooth_score(ratio), 1)

    if ratio >= 1.5:
        status, color = "Excellent", "green"
    elif ratio >= 1.0:
        status, color = "Healthy", "green"
    elif ratio >= 0.5:
        status, color = "Below Average", "yellow"
    else:
        status, color = "Suspicious", "red"

    # ---- Suspicious Pattern Detection ----
    flags = []

    if like_comment_ratio is not None and like_comment_ratio > 500:
        flags.append("Extremely low comments relative to likes")

    if engagement_rate == 0 and followers > 1000:
        flags.append("Zero engagement despite large following")

    if posts == 0:
        flags.append("No posts found")

    if followers > 100000 and comments_avg < 5 and not comments_off:
        flags.append("Large account with almost no comments")

    return {
        "engagement_rate":    engagement_rate,
        "benchmark":          benchmark,
        "tier":               tier,
        "status":             status,
        "color":              color,
        "engagement_score":   engagement_score,
        "like_comment_ratio": round(like_comment_ratio, 2) if like_comment_ratio is not None else None,
        "comments_off":       bool(comments_off),
        "flags":              flags,
        "total_flags":        len(flags),
        "measured":           True,
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