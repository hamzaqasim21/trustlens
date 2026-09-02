# TrustLens — Misinformation Classifier

## Note on excluded files
The following are excluded from this repository due to file size limits (GitHub blocks files over 100MB):

- `api/model/model.safetensors` (~1.1GB) — the trained model weights. Available on request via Google Drive.
- `CoAID/`, `LIAR/`, `SMSSpam/` raw dataset folders — publicly available from their original sources:
  - CoAID: https://github.com/cuilimeng/CoAID
  - LIAR: https://www.cs.ucsb.edu/~william/data/liar_dataset.zip
  - SMS Spam Collection: https://archive.ics.uci.edu/dataset/228/sms+spam+collection

All code (`scripts/`, `api/`) needed to reproduce the dataset and retrain the model is included in this repo. The processed `unified_dataset.csv` is included.