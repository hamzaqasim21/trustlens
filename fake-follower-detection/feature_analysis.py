"""
TrustLens - Fake Follower Detection
Which attributes actually decide whether an account is Real or Fake?

Runs three complementary analyses on master_dataset.csv:
  1. Average value of each raw attribute for REAL vs FAKE accounts.
  2. Correlation of each raw attribute with the 'fake' label
     (positive -> higher value pushes toward FAKE).
  3. The trained model's own feature-importance ranking.

Saves two charts into artifacts/ for the report / slides.
"""
import json

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from predict_core import RAW_FEATURES, RAW_LABELS, ARTIFACT_DIR

df = pd.read_csv("master_dataset.csv")
real = df[df["fake"] == 0]
fake = df[df["fake"] == 1]

print("=" * 68)
print(f"MASTER DATASET  |  {len(df):,} accounts  "
      f"({len(real):,} real, {len(fake):,} fake)")
print("=" * 68)

# ---- 1 + 2. Real-vs-Fake averages and correlation with the label ----
rows = []
for k in RAW_FEATURES:
    corr = df[k].corr(df["fake"])          # point-biserial (label is 0/1)
    rows.append({
        "attribute": RAW_LABELS[k],
        "avg_real": round(real[k].mean(), 3),
        "avg_fake": round(fake[k].mean(), 3),
        "corr_with_fake": round(corr, 3),
        "pushes_toward": "FAKE" if corr > 0 else "REAL",
    })
raw_tbl = pd.DataFrame(rows).sort_values("corr_with_fake", key=abs, ascending=False)
print("\n1) Average value per class + correlation with the FAKE label")
print("   (|correlation| high = attribute separates the classes well)\n")
print(raw_tbl.to_string(index=False))

# ---- 3. Model feature importance ----
imp = pd.read_csv(ARTIFACT_DIR / "feature_importance.csv")
print("\n2) XGBoost feature importance (top 10 of 18 engineered features)\n")
print(imp.head(10).to_string(index=False))

# ---- Charts ----
ARTIFACT_DIR.mkdir(exist_ok=True)

# Chart A: model importance
top = imp.head(10).iloc[::-1]
fig, ax = plt.subplots(figsize=(7, 4.5))
ax.barh(top["feature"], top["importance"], color="#2563eb")
ax.set_title("Top features driving Real/Fake classification (XGBoost)")
ax.set_xlabel("Importance")
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.tight_layout()
fig.savefig(ARTIFACT_DIR / "feature_importance.png", dpi=130, transparent=False)
print(f"\nSaved chart -> {ARTIFACT_DIR / 'feature_importance.png'}")

# Chart B: real vs fake averages (log scale, since counts vary hugely)
labels = [RAW_LABELS[k] for k in RAW_FEATURES]
x = np.arange(len(labels))
fig, ax = plt.subplots(figsize=(9, 4.5))
ax.bar(x - 0.2, [real[k].mean() for k in RAW_FEATURES], 0.4,
       label="Real", color="#16a34a")
ax.bar(x + 0.2, [fake[k].mean() for k in RAW_FEATURES], 0.4,
       label="Fake", color="#dc2626")
ax.set_yscale("symlog")
ax.set_xticks(x)
ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
ax.set_ylabel("Average (symlog scale)")
ax.set_title("Average attribute value: Real vs Fake accounts")
ax.legend()
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
fig.tight_layout()
fig.savefig(ARTIFACT_DIR / "real_vs_fake.png", dpi=130)
print(f"Saved chart -> {ARTIFACT_DIR / 'real_vs_fake.png'}")

# Save the raw table too
raw_tbl.to_csv(ARTIFACT_DIR / "attribute_analysis.csv", index=False)
print(f"Saved table -> {ARTIFACT_DIR / 'attribute_analysis.csv'}")

print("\nPlain-English summary for the supervisor:")
print("  - Followers count / log_followers is the single strongest signal.")
print("  - Fake accounts follow MANY people but have FEW followers "
      "(high follows-to-followers ratio).")
print("  - Fake accounts post less, have shorter/empty bios, and more digits "
      "in the username.")
print("  - Missing profile picture strongly indicates a fake/bot account.")
