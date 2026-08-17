"""
prepare_data.py
----------------
Merges CoAID (health misinformation), LIAR (political propaganda), and
the SMS Spam Collection (financial scam / manipulative-language proxy)
into a single unified training set for the TrustLens Misinformation
Classifier.

NOTE on financial_scam: no freely-downloadable dataset of real
Instagram-style investment-scam captions exists without scraping or a
login-walled source. SMS Spam Collection is used as a linguistic proxy
(prize scams, urgency, "call now" manipulation) — document this as a
known limitation in your report; swap in real scraped captions later.

Output schema (data/unified_dataset.csv):
    text      -> the raw text to classify (caption/claim/article/message)
    category  -> "health_misinformation" | "political_propaganda" | "financial_scam"
    label     -> 1 = misinformation/scam, 0 = credible/real
    source    -> which raw dataset this row came from (for traceability)

Run from the misinfo_classifier/ directory:
    python scripts/prepare_data.py --coaid_dir ../CoAID --liar_dir ../LIAR --smsspam_path ../SMSSpam/sms.tsv --out data/unified_dataset.csv
"""

import argparse
import glob
import os
import re
import pandas as pd


def clean_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    # Cap very long article bodies — captions/claims are short anyway,
    # and XLM-R truncates at 512 tokens during training regardless.
    return text[:2000]


def load_coaid(coaid_dir: str) -> pd.DataFrame:
    """
    Loads every NewsFake/NewsReal/ClaimFake/ClaimReal CSV across all
    CoAID date snapshots and labels them for the health_misinformation
    category. label=1 for Fake, label=0 for Real.
    """
    rows = []
    news_files = glob.glob(os.path.join(coaid_dir, "*", "News*COVID-19.csv"))
    claim_files = glob.glob(os.path.join(coaid_dir, "*", "Claim*COVID-19.csv"))

    for f in news_files:
        is_fake = "Fake" in os.path.basename(f)
        try:
            df = pd.read_csv(f)
        except Exception as e:
            print(f"  [skip] {f}: {e}")
            continue
        for _, row in df.iterrows():
            title = clean_text(row.get("title", ""))
            content = clean_text(row.get("content", ""))
            text = (title + ". " + content).strip(". ").strip()
            if len(text) < 15:
                continue
            rows.append({
                "text": text,
                "category": "health_misinformation",
                "label": 1 if is_fake else 0,
                "source": "CoAID_News",
            })

    for f in claim_files:
        is_fake = "Fake" in os.path.basename(f)
        try:
            df = pd.read_csv(f)
        except Exception as e:
            print(f"  [skip] {f}: {e}")
            continue
        for _, row in df.iterrows():
            title = clean_text(row.get("title", ""))
            if len(title) < 10:
                continue
            rows.append({
                "text": title,
                "category": "health_misinformation",
                "label": 1 if is_fake else 0,
                "source": "CoAID_Claim",
            })

    df = pd.DataFrame(rows).drop_duplicates(subset="text")
    print(f"CoAID -> {len(df)} rows "
          f"({(df.label == 1).sum()} fake / {(df.label == 0).sum()} real)")
    return df


# LIAR's 6-way truthfulness scale collapsed to binary — this is the
# standard collapse used across LIAR literature (see e.g. Wang 2017
# follow-up work): the 3 "leans false" grades -> misinformation (1),
# the 3 "leans true" grades -> credible (0).
LIAR_LABEL_MAP = {
    "pants-fire": 1,
    "false": 1,
    "barely-true": 1,
    "half-true": 0,
    "mostly-true": 0,
    "true": 0,
}

LIAR_COLUMNS = [
    "id", "label", "statement", "subject", "speaker", "job", "state",
    "party", "barely_true_c", "false_c", "half_true_c", "mostly_true_c",
    "pants_on_fire_c", "venue",
]


def load_liar(liar_dir: str) -> pd.DataFrame:
    rows = []
    for split in ["train.tsv", "valid.tsv", "test.tsv"]:
        path = os.path.join(liar_dir, split)
        if not os.path.exists(path):
            print(f"  [skip] {path} not found")
            continue
        df = pd.read_csv(path, sep="\t", header=None, names=LIAR_COLUMNS)
        for _, row in df.iterrows():
            raw_label = str(row["label"]).strip().lower()
            if raw_label not in LIAR_LABEL_MAP:
                continue
            text = clean_text(row["statement"])
            if len(text) < 10:
                continue
            rows.append({
                "text": text,
                "category": "political_propaganda",
                "label": LIAR_LABEL_MAP[raw_label],
                "source": f"LIAR_{split.split('.')[0]}",
            })
    df = pd.DataFrame(rows).drop_duplicates(subset="text")
    print(f"LIAR  -> {len(df)} rows "
          f"({(df.label == 1).sum()} misinfo / {(df.label == 0).sum()} credible)")
    return df


def load_smsspam(path: str) -> pd.DataFrame:
    """
    Loads the SMS Spam Collection (label \\t message, tab-separated,
    no header) and maps spam -> financial_scam (label=1),
    ham -> credible (label=0).
    """
    if not os.path.exists(path):
        print(f"  [skip] {path} not found")
        return pd.DataFrame(columns=["text", "category", "label", "source"])

    df = pd.read_csv(path, sep="\t", header=None, names=["raw_label", "message"])
    rows = []
    for _, row in df.iterrows():
        text = clean_text(row["message"])
        if len(text) < 10:
            continue
        is_scam = str(row["raw_label"]).strip().lower() == "spam"
        rows.append({
            "text": text,
            "category": "financial_scam",
            "label": 1 if is_scam else 0,
            "source": "SMSSpam",
        })
    out = pd.DataFrame(rows).drop_duplicates(subset="text")
    print(f"SMSSpam -> {len(out)} rows "
          f"({(out.label == 1).sum()} scam / {(out.label == 0).sum()} credible)")
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--coaid_dir", default="../CoAID")
    parser.add_argument("--liar_dir", default="../LIAR")
    parser.add_argument("--smsspam_path", default="../SMSSpam/sms.tsv")
    parser.add_argument("--out", default="data/unified_dataset.csv")
    args = parser.parse_args()

    print("Loading CoAID (health_misinformation)...")
    coaid_df = load_coaid(args.coaid_dir)

    print("Loading LIAR (political_propaganda)...")
    liar_df = load_liar(args.liar_dir)

    print("Loading SMS Spam Collection (financial_scam proxy)...")
    scam_df = load_smsspam(args.smsspam_path)

    combined = pd.concat([coaid_df, liar_df, scam_df], ignore_index=True)
    combined = combined.sample(frac=1, random_state=42).reset_index(drop=True)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    combined.to_csv(args.out, index=False)

    print(f"\nSaved {len(combined)} total rows -> {args.out}")
    print("\nBreakdown by category x label:")
    print(combined.groupby(["category", "label"]).size())


if __name__ == "__main__":
    main()
