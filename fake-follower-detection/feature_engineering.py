import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split

# ---- Load merged master dataset ----
df = pd.read_csv("master_dataset.csv")

# ---- Step 1: Train/test split FIRST, before any threshold-based features ----
# Yeh split threshold-calculation se pehle hona ZAROORI hai, warna test-set
# ki information training thresholds mein leak ho jayegi.
train_df, test_df = train_test_split(
    df, test_size=0.2, stratify=df["fake"], random_state=42
)
train_df = train_df.copy()
test_df = test_df.copy()


def add_row_wise_features(data):
    """Row-wise transforms — train/test pe independently safe hain,
    koi aggregate statistic involved nahi, isliye leakage risk nahi."""
    data = data.copy()
    data["log_followers"] = np.log1p(data["followers_count"])
    data["log_follows"] = np.log1p(data["follows_count"])
    data["log_posts"] = np.log1p(data["posts_count"])
    data["followers_per_post"] = data["followers_count"] / (data["posts_count"] + 1)
    data["follows_to_followers"] = data["follows_count"] / (data["followers_count"] + 1)
    # NOTE: "engagement_ratio" aur "social_reach" Khan et al. (2026) ke
    # confirmed feature-NAMES hain, lekin paper exact formula publish nahi karta.
    # Yeh standard, literature-consistent constructions hain, verified formula nahi.
    data["engagement_ratio"] = data["posts_count"] / (data["followers_count"] + data["follows_count"] + 1)
    data["social_reach"] = data["followers_count"] / (data["followers_count"] + data["follows_count"] + 1)
    data["has_no_posts"] = (data["posts_count"] == 0).astype(int)
    return data


train_df = add_row_wise_features(train_df)
test_df = add_row_wise_features(test_df)

# ---- Step 2: Percentile thresholds — SIRF TRAIN se calculate ----
follows_threshold = train_df["follows_count"].quantile(0.90)
followers_threshold = train_df["followers_count"].quantile(0.90)

print(f"has_many_follows threshold (90th percentile, train only): {follows_threshold}")
print(f"has_many_followers threshold (90th percentile, train only): {followers_threshold}")

for data in [train_df, test_df]:
    data["has_many_follows"] = (data["follows_count"] > follows_threshold).astype(int)
    data["has_many_followers"] = (data["followers_count"] > followers_threshold).astype(int)
    data["follow_activity_score"] = (
        data["has_no_posts"] + data["has_many_follows"] + (data["follows_to_followers"] > 1).astype(int)
    )

feature_cols = [
    "profile_pic", "username_digit_ratio", "description_length", "private",
    "posts_count", "followers_count", "follows_count",
    "log_followers", "log_follows", "log_posts",
    "followers_per_post", "follows_to_followers", "engagement_ratio",
    "social_reach", "has_no_posts", "has_many_follows",
    "has_many_followers", "follow_activity_score",
]

print("\nTrain shape:", train_df.shape, "| Test shape:", test_df.shape)
print("\nTrain class balance:\n", train_df["fake"].value_counts())
print("\nTest class balance:\n", test_df["fake"].value_counts())
print("\nNulls in train?", train_df[feature_cols].isnull().sum().sum())
print("Nulls in test?", test_df[feature_cols].isnull().sum().sum())

train_df.to_csv("train_engineered.csv", index=False)
test_df.to_csv("test_engineered.csv", index=False)
print("\nSaved train_engineered.csv and test_engineered.csv")