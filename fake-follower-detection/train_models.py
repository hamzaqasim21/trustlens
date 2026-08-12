import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, classification_report, confusion_matrix
from imblearn.over_sampling import SMOTE
import xgboost as xgb

# ---- Load engineered data ----
train_df = pd.read_csv("train_engineered.csv")
test_df = pd.read_csv("test_engineered.csv")

feature_cols = [
    "profile_pic", "username_digit_ratio", "description_length", "private",
    "posts_count", "followers_count", "follows_count",
    "log_followers", "log_follows", "log_posts",
    "followers_per_post", "follows_to_followers", "engagement_ratio",
    "social_reach", "has_no_posts", "has_many_follows",
    "has_many_followers", "follow_activity_score",
]

X_train_raw = train_df[feature_cols]
y_train = train_df["fake"]
X_test_raw = test_df[feature_cols]
y_test = test_df["fake"]

# ---- Scale BEFORE SMOTE ----
# SMOTE nearest-neighbours interpolate karta hai feature space mein — agar
# features alag scale pe hain (followers_count hazaron mein vs profile_pic 0/1),
# to large-scale features distance-calculation ko dominate kar denge. Isliye
# pehle scale karna zaroori hai.
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train_raw)
X_test_scaled = scaler.transform(X_test_raw)

# ---- SMOTE — SIRF training data pe ----
smote = SMOTE(random_state=42)
X_train_bal, y_train_bal = smote.fit_resample(X_train_scaled, y_train)

print("Before SMOTE:", y_train.value_counts().to_dict())
print("After SMOTE:", pd.Series(y_train_bal).value_counts().to_dict())

results = {}

def evaluate(name, y_true, y_pred):
    acc = accuracy_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred, average="macro")
    results[name] = {"accuracy": acc, "f1_macro": f1}
    print(f"\n=== {name} ===")
    print("Accuracy:", round(acc, 4), "| F1-macro:", round(f1, 4))
    print(confusion_matrix(y_true, y_pred))
    print(classification_report(y_true, y_pred, target_names=["Real", "Fake"]))

# ---- Random Forest ----
rf = RandomForestClassifier(n_estimators=300, max_depth=12, random_state=42, n_jobs=-1)
rf.fit(X_train_bal, y_train_bal)
evaluate("Random Forest", y_test, rf.predict(X_test_scaled))

# ---- XGBoost ----
xgb_clf = xgb.XGBClassifier(
    n_estimators=300, max_depth=6, learning_rate=0.1,
    eval_metric="logloss", random_state=42
)
xgb_clf.fit(X_train_bal, y_train_bal)
evaluate("XGBoost", y_test, xgb_clf.predict(X_test_scaled))

# ---- LSTM (tabular data ko length-1 sequence ki tarah reshape kiya — 
#      yeh standard practice hai jab sequence models ko tabular data pe 
#      apply karte hain, jaisa current-field papers mein hota hai) ----
import tensorflow as tf
from tensorflow.keras import layers, models

X_train_lstm = X_train_bal.reshape((X_train_bal.shape[0], 1, X_train_bal.shape[1]))
X_test_lstm = X_test_scaled.reshape((X_test_scaled.shape[0], 1, X_test_scaled.shape[1]))

lstm_model = models.Sequential([
    layers.Input(shape=(1, X_train_bal.shape[1])),
    layers.LSTM(32, return_sequences=False),
    layers.Dropout(0.3),
    layers.Dense(16, activation="relu"),
    layers.Dense(1, activation="sigmoid"),
])
lstm_model.compile(optimizer="adam", loss="binary_crossentropy", metrics=["accuracy"])
lstm_model.fit(X_train_lstm, y_train_bal, epochs=25, batch_size=16, verbose=0)

lstm_preds = (lstm_model.predict(X_test_lstm, verbose=0) > 0.5).astype(int).flatten()
evaluate("LSTM", y_test, lstm_preds)

# ---- Final comparison table ----
print("\n\n=== FINAL COMPARISON ===")
comparison_df = pd.DataFrame(results).T
print(comparison_df)