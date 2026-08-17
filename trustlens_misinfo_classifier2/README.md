# TrustLens — Misinformation Classifier Module

Your module of the TrustLens project: a fine-tuned XLM-RoBERTa model that
classifies social media text into credible / health_misinformation /
political_propaganda / financial_scam, served via FastAPI, with a basic
HTML test console.

## Folder structure

    data/       -> unified_dataset.csv (health + political + financial scam, already merged)
    scripts/    -> prepare_data.py (rebuild the dataset) and train_model.py (run on Colab)
    api/        -> FastAPI backend (main.py, model_loader.py, instagram_fetch.py)
    api/model/  -> put your Colab-trained model files here (see api/model/README.md)
    frontend/   -> index.html test console (paste text, or pull a live Instagram profile)

## Quick start (after opening this folder in VS Code)

1. Train on Google Colab using `scripts/train_model.py` + `data/unified_dataset.csv`
2. Download the trained model, unzip it into `api/model/` (see api/model/README.md)
3. In VS Code terminal:
   ```
   cd api
   python3 -m venv venv
   source venv/bin/activate      # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env          # then paste in your teammate's RAPIDAPI_KEY
   uvicorn main:app --reload --port 8000
   ```
4. Open `frontend/index.html` in your browser (or right-click -> Open with Live Server in VS Code)
5. Test with the "Test Raw Text" tab first, then "Test by URL" — paste a profile URL, a post/reel URL, or just a username

## New: /classify-url

POST /classify-url  { "url": "https://www.instagram.com/p/SHORTCODE/" }

Accepts a profile URL, a post/reel URL, or a bare username. Resolves it, fetches ONE real post (the latest one, for profile URLs), and classifies its caption. This is the endpoint the frontend's "Test by URL" tab calls.

NOTE: single-post-by-shortcode fetching (api/instagram_fetch.py -> fetch_post_by_shortcode) uses a best-guess endpoint name since I couldn't verify it against a live API key. If pasting a /p/ or /reel/ URL fails, check RapidAPI's actual docs for the instagram-scraper-stable-api's single-post endpoint and update the two constants at the top of that function. Profile URLs and usernames use the already-confirmed-working get_ig_user_posts.php endpoint, so those should work out of the box.

## API contract (for syncing with your teammate's Trust Score Engine)

POST /classify  { "text": "..." }  ->

    {
      "status": "success",
      "misinformation_flag": true,
      "primary_category": "financial_scam",
      "confidence": 0.87,
      "category_scores": { "credible": 0.05, "health_misinformation": 0.03,
                            "political_propaganda": 0.05, "financial_scam": 0.87 },
      "risk_score": 82
    }
