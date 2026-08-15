# TrustLens — Fake Follower Detection

Module 6.4 of the TrustLens FYP · Ali Ahmad (231667) · Air University Islamabad · FCAI 2025-26

Classifies a public Instagram account as **Real** or **Fake / bot-like** from seven
account-level attributes, with an *Uncertain* band when the model is not confident enough.

```
username or profile URL -> Apify -> 7 raw features -> 18 engineered features
                                                              |
                                        StandardScaler -> XGBoost -> Real / Fake / Uncertain
```

## Dataset

Two public datasets merged down to their shared attributes:

| Source | Format | Contents |
|---|---|---|
| InstaFake (Akyon & Kalfaoglu) | JSON | real and fake accounts |
| IFSG / Goyal | CSV | real and fake accounts |

Result: **1,890 accounts** — 1,342 real, 548 fake.

## Results

Held-out test set of 378 accounts:

| Model | Accuracy | F1-macro |
|---|---|---|
| Random Forest | 93.4% | 0.921 |
| **XGBoost** | **94.4%** | **0.933** |
| LSTM | 93.7% | 0.924 |

XGBoost is saved as the production model.

### Attribute contribution

Correlation of each raw attribute with the fake label:

| Attribute | Avg real | Avg fake | Correlation |
|---|---:|---:|---:|
| Has profile picture | 0.99 | 0.49 | −0.62 |
| Digits in username | 0.03 | 0.24 | +0.57 |
| Private account | 0.65 | 0.31 | −0.31 |
| Bio length | 29 | 7.5 | −0.28 |
| Posts | 102 | 6.7 | −0.18 |
| Following | 567 | 938 | +0.16 |

By XGBoost importance: `log_followers` (37%), `log_posts` (18%), `profile_pic` (10%),
`follows_to_followers` (9%).

## Features

Seven raw attributes are read from each profile:

| Feature | Meaning |
|---|---|
| `profile_pic` | has a profile picture |
| `username_digit_ratio` | digits ÷ username length |
| `description_length` | characters in the bio |
| `private` | account is private |
| `posts_count` | total posts |
| `followers_count` | total followers |
| `follows_count` | accounts followed |

These expand to 18 engineered features — log transforms, ratios such as
`follows_to_followers` and `engagement_ratio`, and percentile-threshold flags.

The train/test split happens **before** the percentile thresholds are computed, so no test
data influences them. SMOTE is applied to the training split only.

## Files

| File | Purpose |
|---|---|
| `merge.py` | Merge the two datasets into `master_dataset.csv` |
| `feature_engineering.py` | Split and build the engineered features |
| `train_models.py` | Compare RandomForest, XGBoost and LSTM |
| `train_and_save.py` | Train the production model and write `artifacts/` |
| `predict_core.py` | Shared feature logic and model loading |
| `apify_scraper.py` | Fetch a profile through Apify |
| `check_user.py` | Command-line interface |
| `app.py` | Streamlit interface |
| `feature_analysis.py` | Attribute analysis and charts |

## Setup

```
pip install -r requirements.txt
```

Set the Apify token before any live lookup:

```
$env:APIFY_API_TOKEN = "apify_api_..."
```

## Usage

Rebuild the dataset and model:

```
python merge.py
python feature_engineering.py
python train_and_save.py
```

Check an account:

```
streamlit run app.py
python check_user.py <username or profile URL>
python check_user.py --manual
```

The input accepts a username, `@username`, or a full profile URL. Post and reel links are
rejected because they do not identify a single profile.

## Notes

- Results are cached per username in `cache/` to avoid repeat API calls.
- Below 60% confidence the module reports *Uncertain* rather than a verdict.
- Small or new accounts often fall in that band: they resemble low-follower fake accounts
  statistically.
- Apify almost always returns a profile picture URL, so `profile_pic` carries less weight on
  live lookups than it does on the training data.
- The module classifies individual accounts. Scoring a whole follower network with graph
  metrics is a separate piece of work.
