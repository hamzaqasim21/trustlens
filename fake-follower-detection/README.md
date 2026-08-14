# TrustLens — Fake Follower Detection Module

Module 6.4 of the **TrustLens** FYP. Given any public Instagram account, it
extracts 7 account-level features and classifies the account as **Real** or
**Fake / bot-like** using machine-learning models trained on two merged public
datasets.

**Owner:** Ali Ahmad

---

## 1. What it does

```
Instagram username ──► Apify scraper ──► 7 raw features ──► feature engineering
                                                                     │
                                                                     ▼
                                        StandardScaler ──► XGBoost ──► Real / Fake / Uncertain + confidence
```

Verdicts use a **3-way band** (matching the scope document's *Wrong Score
Handling* policy): confident **Real** / confident **Fake** / **Uncertain –
needs review** when model confidence is below 60%.

Trained on **1,890 accounts** (1,342 real, 548 fake). Best model (XGBoost)
scores **94.4% accuracy / 0.93 F1-macro** on a held-out test set.

---

## 2. Project files

| File | Purpose |
|------|---------|
| `merge.py` | Merge **InstaFake** (JSON) + **IFSG/Goyal** (CSV) into `master_dataset.csv` |
| `feature_engineering.py` | Train/test split, build 18 engineered features (no data leakage) |
| `train_models.py` | Train & compare RandomForest, XGBoost, LSTM |
| `train_and_save.py` | Re-train the best model and **save it** to `artifacts/` for prediction |
| `predict_core.py` | Shared feature logic + model load/save (used by CLI **and** web app) |
| `apify_scraper.py` | Fetch a real Instagram profile via Apify, map to the 7 features |
| `check_user.py` | **CLI demo** — classify a username in the terminal |
| `app.py` | **Web demo** — Streamlit UI |
| `feature_analysis.py` | Which attributes decide Real vs Fake (charts + tables) |
| `artifacts/` | Saved model, scaler, thresholds, feature-importance charts |

---

## 3. The 7 raw features (extractable for ANY public profile)

| Feature | Meaning |
|---------|---------|
| `profile_pic` | Has a profile picture (1/0) |
| `username_digit_ratio` | digits ÷ username length |
| `description_length` | number of characters in the bio |
| `private` | account is private (1/0) |
| `posts_count` | total posts |
| `followers_count` | total followers |
| `follows_count` | total accounts followed |

These are expanded into **18 engineered features** (log transforms, ratios like
`follows_to_followers`, `engagement_ratio`, percentile-threshold flags) — see
`feature_engineering.py` / `predict_core.py`.

## 4. Which attributes matter

Correlation of each raw attribute with the **fake** label (from `feature_analysis.py`):

| Attribute | Avg Real | Avg Fake | Corr. w/ fake | Signal |
|-----------|---------:|---------:|--------------:|--------|
| Has profile picture | 0.99 | 0.49 | **−0.62** | no picture ⇒ fake |
| Digits in username | 0.03 | 0.24 | **+0.57** | more digits ⇒ fake |
| Private account | 0.65 | 0.31 | −0.31 | real more often private |
| Bio length | 29 | 7.5 | −0.28 | real = longer bios |
| Posts | 102 | 6.7 | −0.18 | real posts more |
| Following | 567 | 938 | +0.16 | fake follows more |

XGBoost's own top features: `log_followers` (37%), `log_posts` (18%),
`profile_pic` (10%), `follows_to_followers` (9%).

---

## 5. Setup (one time)

```bash
pip install -r requirements.txt
```

Get a free **Apify** token: sign in at https://apify.com → *Settings → API & Integrations*
→ copy the **Personal API token** (`apify_api_...`).

Set it for the session (do **not** paste it into any file):

```powershell
$env:APIFY_API_TOKEN = "apify_api_xxxxxxxxxxxxxxxxx"
```

---

## 6. Run the whole pipeline

```bash
python merge.py                # build master_dataset.csv
python feature_engineering.py  # build engineered train/test sets
python train_models.py         # compare RF / XGBoost / LSTM
python train_and_save.py       # save the best model to artifacts/
python feature_analysis.py     # attribute analysis + charts
```

## 7. Demo — check a real user

**Web app (recommended):**
```bash
streamlit run app.py
```
→ type a username (e.g. `ali.ahmad.r8`) → **Analyze**.

**Command line:**
```bash
python check_user.py ali.ahmad.r8
```

**Offline / no token (backup):**
```bash
python check_user.py --manual
```

---

## 8. demo flow

1. Open the **web app**, go to *How the model works* — show the 1,890-account
   dataset, the two merged sources, feature importance, and 94.4% accuracy.
2. Switch to *Check an account*, enter an **established** account (many
   followers, e.g. a public figure) → **REAL** with high confidence.
3. Enter a known bot / spam account (or use manual mode with 20 followers /
   3000 following) → **FAKE**.
4. Enter a **small / brand-new** account (e.g. `ali.ahmad.r8`) → **UNCERTAIN**
   — a good chance to explain the 60%-confidence review band from the scope doc.
5. Explain **why**: point at the profile-picture, digit-ratio, and
   follows-to-followers signals in the comparison table.

## 9. Notes & honest limitations

- This module classifies an **individual account** (real vs fake). The scope
  document also describes a graph/Manhattan-distance approach for scoring a
  whole follower base — that is a natural next step built on this classifier.
- Apify almost always returns a profile-picture URL, so `profile_pic` is usually
  1 for live scrapes; the strongest live signals are follower/following/posts
  counts and the username digit ratio.
- The model is trained on public research datasets; it is a strong baseline, not
  a ground-truth oracle. Confidence is shown with every verdict.

---

## 10. Deploy the web app (free — Streamlit Community Cloud)

This module lives in **`fake-follower-detection/`** inside the team repo
`hamzaqasim21/trustlens`. To deploy just this app:

1. Go to **https://share.streamlit.io** → sign in with GitHub → **Create app**.
2. Repo `hamzaqasim21/trustlens`, branch `main`, main file path
   **`fake-follower-detection/app.py`** → **Deploy**.
3. In the app's **⋮ → Settings → Secrets**, paste:
   ```toml
   APIFY_API_TOKEN = "apify_api_xxxxxxxx"
   ```
4. You get a public `https://<name>.streamlit.app` URL.

`artifacts/` (the trained model) **is** committed so the cloud app runs without
retraining. Your Apify token is **never** committed — it lives only in Streamlit
Secrets. All file paths are resolved relative to the app file, so the subfolder
deploy works correctly.

