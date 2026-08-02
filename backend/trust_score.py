# ============================================================
# TrustLens — Trust Score Engine
# ============================================================

def calculate_trust_score(bot_percentage, engagement_score):

    # ---- Convert bot percentage to a 0-100 score ----
    # High bot percentage = low score
    fake_follower_score = max(0, 100 - bot_percentage)

    # ---- Weights from Scope Document ----
    WEIGHT_FAKE_FOLLOWERS = 0.25
    WEIGHT_ENGAGEMENT     = 0.20
    # Remaining modules not yet built — distribute weight
    WEIGHT_REMAINING      = 0.55

    # ---- Calculate weighted score ----
    # Remaining modules get average score of 70 as placeholder
    PLACEHOLDER_SCORE = 70

    weighted_score = (
        fake_follower_score * WEIGHT_FAKE_FOLLOWERS +
        engagement_score    * WEIGHT_ENGAGEMENT     +
        PLACEHOLDER_SCORE   * WEIGHT_REMAINING
    )

    final_score = round(weighted_score, 1)

    # ---- Kill Switch ----
    # If bot percentage is extremely high override score
    if bot_percentage >= 85:
        final_score = max(final_score, 0)
        final_score = min(final_score, 15)

    # ---- Verdict ----
    if final_score >= 70:
        verdict      = "Trusted"
        color        = "green"
        emoji        = "✅"
        description  = "This account appears authentic and credible"
    elif final_score >= 40:
        verdict      = "Moderate Risk"
        color        = "yellow"
        emoji        = "🟡"
        description  = "Some suspicious signals detected — verify before trusting"
    else:
        verdict      = "High Risk"
        color        = "red"
        emoji        = "🔴"
        description  = "Multiple fraud signals detected - do not trust this account"