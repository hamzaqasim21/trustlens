"""
train_model.py
---------------
Fine-tunes XLM-RoBERTa (base) as a 6-class misinformation classifier
for TrustLens.

Classes:
    0 -> credible / not misinformation
    1 -> health_misinformation
    2 -> political_propaganda
    3 -> financial_scam
    4 -> sensational_clickbait
    5 -> urdu_misinformation

Designed to run in Google Colab with a free GPU runtime.
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

LABEL_NAMES = [
    "credible",
    "health_misinformation",
    "political_propaganda",
    "financial_scam",
    "sensational_clickbait",
    "urdu_misinformation",
]
CATEGORY_TO_CLASS = {
    "health_misinformation": 1,
    "political_propaganda": 2,
    "financial_scam": 3,
    "sensational_clickbait": 4,
    "urdu_misinformation": 5,
}
MODEL_NAME = "xlm-roberta-base"
MAX_LENGTH = 384


def build_target_label(row):
    if row["label"] == 0:
        return 0
    return CATEGORY_TO_CLASS[row["category"]]


def load_and_split(data_path):
    df = pd.read_csv(data_path)
    df["target"] = df.apply(build_target_label, axis=1)
    train_df, temp_df = train_test_split(df, test_size=0.2, stratify=df["target"], random_state=42)
    val_df, test_df = train_test_split(temp_df, test_size=0.5, stratify=temp_df["target"], random_state=42)
    print(f"Train: {len(train_df)}  Val: {len(val_df)}  Test: {len(test_df)}")
    print("Train class distribution:\n", train_df["target"].value_counts())
    return train_df, val_df, test_df


def tokenize_dataset(df, tokenizer):
    ds = Dataset.from_pandas(df[["text", "target"]].rename(columns={"target": "labels"}))

    def _tok(batch):
        return tokenizer(batch["text"], truncation=True, padding="max_length", max_length=MAX_LENGTH)

    ds = ds.map(_tok, batched=True)
    ds.set_format(type="torch", columns=["input_ids", "attention_mask", "labels"])
    return ds


class WeightedTrainer(Trainer):
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


data_path = "unified_dataset.csv"
output_dir = "./trustlens_misinfo_model"
epochs = 4
batch_size = 16

train_df, val_df, test_df = load_and_split(data_path)

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
train_ds = tokenize_dataset(train_df, tokenizer)
val_ds = tokenize_dataset(val_df, tokenizer)
test_ds = tokenize_dataset(test_df, tokenizer)

model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=len(LABEL_NAMES))

class_weights = compute_class_weight(class_weight="balanced", classes=np.array([0, 1, 2, 3, 4, 5]), y=train_df["target"].values)
class_weights = torch.tensor(class_weights, dtype=torch.float)
print("Class weights:", dict(zip(LABEL_NAMES, class_weights.tolist())))

training_args = TrainingArguments(
    output_dir="./checkpoints",
    num_train_epochs=epochs,
    per_device_train_batch_size=batch_size,
    per_device_eval_batch_size=batch_size,
    eval_strategy="epoch",
    save_strategy="epoch",
    load_best_model_at_end=True,
    metric_for_best_model="f1_macro",
    logging_steps=50,
    learning_rate=2e-5,
    weight_decay=0.01,
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