"""
TrustLens - Fake Follower Detection
Train the classifier and SAVE it, so any new Instagram account can be scored
later without retraining.

This reuses the EXACT pipeline from feature_engineering.py + train_models.py:
  1. load master_dataset.csv
  2. split train/test (random_state=42, stratified)  -- split BEFORE thresholds
  3. add row-wise features
  4. learn the 90th-percentile thresholds from TRAIN ONLY
  5. scale (fit on train)  ->  SMOTE on train  ->  train models
  6. evaluate on the untouched test set
  7. save model + scaler + thresholds + feature importance  ->  artifacts/

XGBoost is saved as the production model because it had the best F1-macro,
but RandomForest is also trained here as a cross-check.
"""
import json

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix, classification_report
from imblearn.over_sampling import SMOTE
import xgboost as xgb

from predict_core import (
    FEATURE_COLS, RAW_FEATURES, add_row_wise_features,
    add_threshold_features, save_artifacts,
)

RANDOM_STATE = 42

# ---- 1. Load merged master dataset ----
df = pd.read_csv("master_dataset.csv")
print(f"Master dataset: {df.shape[0]} accounts "
      f"({(df['fake'] == 0).sum()} real, {(df['fake'] == 1).sum()} fake)")

# ---- 2. Split FIRST (before any threshold is computed -> no leakage) ----
train_df, test_df = train_test_split(
    df, test_size=0.2, stratify=df["fake"], random_state=RANDOM_STATE
)
train_df = add_row_wise_features(train_df.copy())
test_df = add_row_wise_features(test_df.copy())

# ---- 3. Thresholds from TRAIN ONLY ----
follows_threshold = float(train_df["follows_count"].quantile(0.90))
followers_threshold = float(train_df["followers_count"].quantile(0.90))
print(f"Thresholds (train 90th pct)  follows={follows_threshold:.1f}  "
      f"followers={followers_threshold:.1f}")

train_df = add_threshold_features(train_df, follows_threshold, followers_threshold)
test_df = add_threshold_features(test_df, follows_threshold, followers_threshold)

X_train_raw = train_df[FEATURE_COLS]
y_train = train_df["fake"]
X_test_raw = test_df[FEATURE_COLS]
y_test = test_df["fake"]

# ---- 4. Scale (fit on train) then SMOTE (train only) ----
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train_raw)
X_test_scaled = scaler.transform(X_test_raw)

smote = SMOTE(random_state=RANDOM_STATE)
X_train_bal, y_train_bal = smote.fit_resample(X_train_scaled, y_train)


def report(name, y_true, y_pred):
    acc = accuracy_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred, average="macro")
    print(f"\n=== {name} ===")
    print(f"Accuracy: {acc:.4f} | F1-macro: {f1:.4f}")
    print(confusion_matrix(y_true, y_pred))
    print(classification_report(y_true, y_pred, target_names=["Real", "Fake"]))
    return acc, f1


# ---- 5. Train models ----
rf = RandomForestClassifier(n_estimators=300, max_depth=12,
                            random_state=RANDOM_STATE, n_jobs=-1)
rf.fit(X_train_bal, y_train_bal)
rf_acc, rf_f1 = report("Random Forest", y_test, rf.predict(X_test_scaled))

xgb_clf = xgb.XGBClassifier(
    n_estimators=300, max_depth=6, learning_rate=0.1,
    eval_metric="logloss", random_state=RANDOM_STATE,
)
xgb_clf.fit(X_train_bal, y_train_bal)
xgb_acc, xgb_f1 = report("XGBoost", y_test, xgb_clf.predict(X_test_scaled))

# ---- 6. Feature importance (from the saved production model = XGBoost) ----
feat_imp = (
    pd.DataFrame({"feature": FEATURE_COLS, "importance": xgb_clf.feature_importances_})
    .sort_values("importance", ascending=False)
    .reset_index(drop=True)
)
print("\nTop features driving the classification:")
print(feat_imp.head(10).to_string(index=False))

# ---- 7. Save everything needed for live prediction ----
thresholds = {
    "follows_threshold": follows_threshold,
    "followers_threshold": followers_threshold,
}
meta = {
    "model": "XGBoost",
    "test_accuracy": round(xgb_acc, 4),
    "test_f1_macro": round(xgb_f1, 4),
    "rf_test_accuracy": round(rf_acc, 4),
    "rf_test_f1_macro": round(rf_f1, 4),
    "n_accounts": int(df.shape[0]),
    "n_real": int((df["fake"] == 0).sum()),
    "n_fake": int((df["fake"] == 1).sum()),
    "raw_features": RAW_FEATURES,
    "feature_cols": FEATURE_COLS,
}
save_artifacts(xgb_clf, scaler, thresholds, feat_imp, meta)
print("\nSaved -> artifacts/  (model.pkl, scaler.pkl, thresholds.json, "
      "feature_importance.csv, meta.json)")
print("The saved model is XGBoost "
      f"(test accuracy {xgb_acc:.1%}, F1-macro {xgb_f1:.3f}).")
