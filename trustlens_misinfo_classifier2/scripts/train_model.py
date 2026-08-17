"""
train_model.py
---------------
Fine-tunes XLM-RoBERTa (base) as a 3-class misinformation classifier
for TrustLens.

Classes:
    0 -> credible / not misinformation
    1 -> health_misinformation
    2 -> political_propaganda
    3 -> financial_scam

Designed to run in Google Colab with a free GPU runtime.

COLAB SETUP:
    1. Runtime -> Change runtime type -> GPU (T4 is fine)
    2. Upload data/unified_dataset.csv to the Colab file browser
       (or mount Google Drive and point --data_path there)
    3. !pip install transformers datasets scikit-learn accelerate -q
    4. Run this script (or paste it cell-by-cell)

Usage:
    python train_model.py --data_path unified_dataset.csv --output_dir ./trustlens_misinfo_model
"""

import argparse
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_class_weight
from sklearn.metrics import classification_report, f1_score, accuracy_score
from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
)

LABEL_NAMES = ["credible", "health_misinformation", "political_propaganda", "financial_scam"]
CATEGORY_TO_CLASS = {
    "health_misinformation": 1,
    "political_propaganda": 2,
    "financial_scam": 3,
}
MODEL_NAME = "xlm-roberta-base"


def build_target_label(row):
    """Collapses (category, binary label) into the single 4-class target."""
    if row["label"] == 0:
        return 0  # credible, regardless of which dataset it came from
    return CATEGORY_TO_CLASS[row["category"]]


def load_and_split(data_path: str):
    df = pd.read_csv(data_path)
    df["target"] = df.apply(build_target_label, axis=1)

    train_df, temp_df = train_test_split(
        df, test_size=0.2, stratify=df["target"], random_state=42
    )
    val_df, test_df = train_test_split(
        temp_df, test_size=0.5, stratify=temp_df["target"], random_state=42
    )
    print(f"Train: {len(train_df)}  Val: {len(val_df)}  Test: {len(test_df)}")
    print("Train class distribution:\n", train_df["target"].value_counts())
    return train_df, val_df, test_df


def tokenize_dataset(df: pd.DataFrame, tokenizer):
    ds = Dataset.from_pandas(df[["text", "target"]].rename(columns={"target": "labels"}))

    def _tok(batch):
        return tokenizer(batch["text"], truncation=True, padding="max_length", max_length=256)

    ds = ds.map(_tok, batched=True)
    ds.set_format(type="torch", columns=["input_ids", "attention_mask", "labels"])
    return ds


class WeightedTrainer(Trainer):
    """Standard Trainer, but applies class weights in the loss so the
    minority class (health_misinformation, ~16% of its category) isn't
    drowned out by the majority class."""

    def __init__(self, *args, class_weights=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.class_weights = class_weights

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        logits = outputs.logits
        loss_fct = nn.CrossEntropyLoss(weight=self.class_weights.to(logits.device))
        loss = loss_fct(logits, labels)
        return (loss, outputs) if return_outputs else loss


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    return {
        "accuracy": accuracy_score(labels, preds),
        "f1_macro": f1_score(labels, preds, average="macro"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_path", default="unified_dataset.csv")
    parser.add_argument("--output_dir", default="./trustlens_misinfo_model")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch_size", type=int, default=16)
    args = parser.parse_args()

    train_df, val_df, test_df = load_and_split(args.data_path)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    train_ds = tokenize_dataset(train_df, tokenizer)
    val_ds = tokenize_dataset(val_df, tokenizer)
    test_ds = tokenize_dataset(test_df, tokenizer)

    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME, num_labels=len(LABEL_NAMES)
    )

    class_weights = compute_class_weight(
        class_weight="balanced",
        classes=np.array([0, 1, 2, 3]),
        y=train_df["target"].values,
    )
    class_weights = torch.tensor(class_weights, dtype=torch.float)
    print("Class weights:", dict(zip(LABEL_NAMES, class_weights.tolist())))

    training_args = TrainingArguments(
        output_dir="./checkpoints",
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1_macro",
        logging_steps=50,
        learning_rate=2e-5,
        weight_decay=0.01,
        warmup_ratio=0.1,
        fp16=torch.cuda.is_available(),
        report_to="none",
    )

    trainer = WeightedTrainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        compute_metrics=compute_metrics,
        class_weights=class_weights,
    )

    trainer.train()

    print("\n=== Final test set evaluation ===")
    preds = trainer.predict(test_ds)
    y_pred = np.argmax(preds.predictions, axis=-1)
    y_true = test_df["target"].values
    print(classification_report(y_true, y_pred, target_names=LABEL_NAMES))

    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    print(f"\nModel saved to {args.output_dir}")
    print("Download this folder (zip it) — you'll load it in the FastAPI service next.")


if __name__ == "__main__":
    main()
