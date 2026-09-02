"""
prepare_data.py
----------------
Merges CoAID (health misinformation), LIAR (political propaganda),
UrduFake (Urdu-language misinformation, its own category), FakeNewsNet
titles (sensational clickbait), and the SMS Spam Collection (financial
scam / manipulative-language proxy) into a single unified training set
for the TrustLens Misinformation Classifier.

NOTE on financial_scam: no freely-downloadable dataset of real
Instagram-style investment-scam captions exists without scraping or a
login-walled source. SMS Spam Collection is used as a linguistic proxy
(prize scams, urgency, "call now" manipulation) — document this as a
known limitation in your report; swap in real scraped captions later.

NOTE on FakeNewsNet: only headline titles are used (not full article
bodies), since the source articles require live scraping via news_url
and many of the original 2018-era links are dead. Titles alone are a
standard and valid basis for sensational-clickbait detection, since
clickbait is fundamentally a headline phenomenon.

NOTE on UrduFake: given its own "urdu_misinformation" category rather
than being merged into political_propaganda. Merging it with LIAR's
short English political statements initially hurt accuracy on that
category (LIAR is short claims, UrduFake is full news articles in a
different language) — separating them lets the model learn each
style/language cleanly. This is how Urdu-language support is added,
per the project scope.

Output schema (data/unified_dataset.csv):
    text      -> the raw text to classify (caption/claim/article/message/title)
    category  -> "health_misinformation" | "political_propaganda" |
                 "financial_scam" | "sensational_clickbait" |
                 "urdu_misinformation"
    label     -> 1 = misinformation/scam, 0 = credible/real
    source    -> which raw dataset this row came from (for traceability)

Run from the misinfo_classifier/ directory:
    python scripts/prepare_data.py \
        --coaid_dir ../CoAID \
        --liar_dir ../LIAR \
        --smsspam_path ../SMSSpam/sms.tsv \
        --urdufake_dir ../datasets/UrduFake \
        --fakenewsnet_dir ../datasets/FakeNewsNet \
        --out data/unified_dataset.csv
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


def load_urdufake(urdufake_dir: str) -> pd.DataFrame:
    """
    Loads UrduFake ('Bend the Truth') .txt files from Train/Fake,
    Train/Real, Test/Fake, Test/Real subfolders. Given its own
    urdu_misinformation category (see module docstring for why).
    label=1 for Fake, label=0 for Real.
    """
    rows = []
    splits = ["Train", "Test"]
    classes = {"Fake": 1, "Real": 0}

    for split in splits:
        for class_name, label in classes.items():
            folder = os.path.join(urdufake_dir, split, class_name)
            if not os.path.isdir(folder):
                print(f"  [skip] {folder} not found")
                continue
            txt_files = glob.glob(os.path.join(folder, "*.txt"))
            for f in txt_files:
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        text = clean_text(fh.read())
                except Exception as e:
                    print(f"  [skip] {f}: {e}")
                    continue
                if len(text) < 10:
                    continue
                rows.append({
                    "text": text,
                    "category": "urdu_misinformation",
                    "label": label,
                    "source": f"UrduFake_{split}",
                })

    df = pd.DataFrame(rows).drop_duplicates(subset="text")
    print(f"UrduFake -> {len(df)} rows "
          f"({(df.label == 1).sum()} fake / {(df.label == 0).sum()} real)")
    return df


def load_fakenewsnet(fakenewsnet_dir: str) -> pd.DataFrame:
    """
    Loads FakeNewsNet's gossipcop_fake/real and politifact_fake/real
    CSVs, using only the 'title' column (headlines) since full article
    bodies require live scraping via news_url. Mapped into
    sensational_clickbait, since clickbait is fundamentally a headline
    phenomenon. label=1 for *_fake files, label=0 for *_real files.
    """
    rows = []
    files = {
        "gossipcop_fake.csv": 1,
        "gossipcop_real.csv": 0,
        "politifact_fake.csv": 1,
        "politifact_real.csv": 0,
    }

    for filename, label in files.items():
        path = os.path.join(fakenewsnet_dir, filename)
        if not os.path.exists(path):
            print(f"  [skip] {path} not found")
            continue
        try:
            df = pd.read_csv(path)
        except Exception as e:
            print(f"  [skip] {path}: {e}")
            continue
        for _, row in df.iterrows():
            title = clean_text(row.get("title", ""))
            if len(title) < 10:
                continue
            rows.append({
                "text": title,
                "category": "sensational_clickbait",
                "label": label,
                "source": filename.replace(".csv", ""),
            })

    df = pd.DataFrame(rows).drop_duplicates(subset="text")
    print(f"FakeNewsNet -> {len(df)} rows "
          f"({(df.label == 1).sum()} clickbait / {(df.label == 0).sum()} credible)")
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--coaid_dir", default="../CoAID")
    parser.add_argument("--liar_dir", default="../LIAR")
    parser.add_argument("--smsspam_path", default="../SMSSpam/sms.tsv")
    parser.add_argument("--urdufake_dir", default="../datasets/UrduFake")
    parser.add_argument("--fakenewsnet_dir", default="../datasets/FakeNewsNet")
    parser.add_argument("--out", default="data/unified_dataset.csv")
    args = parser.parse_args()

    print("Loading CoAID (health_misinformation)...")
    coaid_df = load_coaid(args.coaid_dir)

    print("Loading LIAR (political_propaganda)...")
    liar_df = load_liar(args.liar_dir)

    print("Loading SMS Spam Collection (financial_scam proxy)...")
    scam_df = load_smsspam(args.smsspam_path)

    print("Loading UrduFake (urdu_misinformation)...")
    urdufake_df = load_urdufake(args.urdufake_dir)

    print("Loading FakeNewsNet titles (sensational_clickbait)...")
    fakenewsnet_df = load_fakenewsnet(args.fakenewsnet_dir)

    combined = pd.concat(
        [coaid_df, liar_df, scam_df, urdufake_df, fakenewsnet_df],
        ignore_index=True
    )
    combined = combined.sample(frac=1, random_state=42).reset_index(drop=True)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    combined.to_csv(args.out, index=False)

    print(f"\nSaved {len(combined)} total rows -> {args.out}")
    print("\nBreakdown by category x label:")
    print(combined.groupby(["category", "label"]).size())


if __name__ == "__main__":
    main()