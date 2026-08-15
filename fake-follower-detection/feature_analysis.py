"""
Attribute analysis for master_dataset.csv: per-class averages, correlation with
the label, and the trained model's feature importance. Saves charts to artifacts/.
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

# Class averages and correlation with the label
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

# Model feature importance
imp = pd.read_csv(ARTIFACT_DIR / "feature_importance.csv")
print("\n2) XGBoost feature importance (top 10 of 18 engineered features)\n")
print(imp.head(10).to_string(index=False))

# Charts
ARTIFACT_DIR.mkdir(exist_ok=True)

# Feature importance
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

raw_tbl.to_csv(ARTIFACT_DIR / "attribute_analysis.csv", index=False)
print(f"Saved table -> {ARTIFACT_DIR / 'attribute_analysis.csv'}")

print("\nSummary:")
print("  - Follower count is the strongest single signal.")
print("  - Fake accounts follow many people but have few followers.")
print("  - Fake accounts post less and have shorter bios.")
print("  - A missing profile picture is a strong fake indicator.")
