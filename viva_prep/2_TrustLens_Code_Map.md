# TrustLens — Code Map

*Where everything lives, what each file does, and what to open when the panel says "show me the code".*

**Rule of thumb:**

- **`frontend/`** is what you see in the browser (React).
- **`backend/`** is the brain (Python / FastAPI).
- **`backend/browser_extension/`** is the Chrome extension and its helper.
- **`backend/archive/`** is old or set-aside work that the app does **not** use.

---

## Part 1 — "Show me X": the quick-jump table

Open the file (Ctrl+P in VS Code, type the file name), then press Ctrl+G and type the line number.

| If the panel asks to see… | Open this file | Go to line | What to say |
|---|---|---|---|
| **The whole scan pipeline, from start to end** | `backend/scan_service.py` | 44 (`analyze_username`) | "This one function fetches the data and runs all four checks and the Trust Score" |
| **The API endpoint the website calls** | `backend/main.py` | 144 (`/analyze-live`) | "The website calls this; it checks you're logged in, then runs the pipeline" |
| **Fake-account model (live)** | `backend/fake_follower.py` | 111 (`analyze_fake_followers`) | "Builds the 16 features and asks the trained Random Forest" |
| **The 16 features** | `backend/fake_follower.py` | 27 (`FEATURE_NAMES`) and 47 (`build_features`) | "These are the account facts the model looks at" |
| **Where the fake-account model was trained** | `backend/train_fake_follower.py` | 77 (`main`) | "200 trees, trained on 576 accounts, tested on 120 unseen accounts: 95.8%" |
| **The fake-account dataset** | `backend/archive/fake_follower_detection_ali/goyal-dataset/train.csv` and `test.csv` | – | "Kaggle 'Instagram fake spammer genuine accounts', 696 accounts" |
| **The trained model file** | `backend/fake_follower_model.pkl` | – | "The saved Random Forest the website loads" |
| **Graph theory + Manhattan distance** | `backend/fake_follower_graph/graph_cluster.py` | 67 (features), 85 (graph), 132 (`cluster_accounts`) | "Distance between every pair, connect the closest, Louvain finds the bot clusters" |
| **Graph method results + picture** | `backend/fake_follower_graph/run_analysis.py`, `follower_network.png` | – | "Run it and it prints precision 94.7% and draws the network" |
| **Engagement analyzer** | `backend/engagement_analyzer.py` | 23 (`analyze_engagement`), 14 (`_smooth_score`), 115 (comments) | "Engagement rate vs the normal rate for that account size" |
| **Misinformation AI (running it)** | `backend/misinfo_classifier/api/model_loader.py` | 78 (`classify_text`) | "Loads the fine-tuned XLM-RoBERTa and classifies a text into 6 classes" |
| **Misinformation AI + rules together** | `backend/misinfo_assessment.py` | 62 (`assess_text`) | "The AI's label is cross-checked against scam red flags before it counts" |
| **The scam red-flag rules** | `backend/red_flags.py` | 42 (the list), 84 (the patterns), 247 (`detect_red_flags`) | "12 hand-written patterns: guaranteed returns, cure claims, fake prizes…" |
| **Where the misinformation model was trained** | `backend/misinfo_classifier/scripts/train_model.py` | – | "Run on Google Colab: XLM-RoBERTa base, 4 epochs, 80/10/10 split" |
| **How the misinformation dataset was built** | `backend/misinfo_classifier/scripts/prepare_data.py` | 64 CoAID, 134 LIAR, 161 SMS, 190 UrduFake, 230 FakeNewsNet | "Each public dataset is loaded and mapped to a category" |
| **The misinformation dataset** | `backend/misinfo_classifier/data/unified_dataset.csv` | – | "46,392 texts, 6 classes" |
| **The trained misinformation model** | `backend/misinfo_classifier/api/model/` | – | "`model.safetensors` is the 1.1 GB trained model (too big for GitHub)" |
| **Credential check (PMDC / NPI)** | `backend/credential_extractor.py` | 46 (find claims), 119 (PMDC), 141 (NPI), 204 (score) | "Finds 'Dr.' / MBBS and looks the name up in the official registers" |
| **Trust Score formula** | `backend/trust_score.py` | 19 (weights), 43 (`calculate_trust_score`), 27 (verdict bands) | "Weights 25/20/25/10, re-balanced to 100%, kill switch at 85% fake" |
| **Instagram data fetching** | `backend/data_ingestion.py` | 52 (profile), 110 (posts), 245 (comments) | "Calls RapidAPI; time limits and retries" |
| **Database tables** | `backend/database.py` | – | "Users, scans, reports, admin log, watchlist, alerts" |
| **Login / security** | `backend/auth.py` | – | "bcrypt password hashing, JWT tokens, admin check" |
| **Admin console API** | `backend/admin.py` | – | "Users, reports, live model test, audit log; every route checks admin on the server" |
| **PDF reports** | `backend/reports.py` | – | "Builds the scan and comparison PDFs with ReportLab" |
| **Watchlist + alerts** | `backend/watchlist.py` | – | "Daily re-check, alert when a score drops 5+ points" |
| **Website: all calls to the backend** | `frontend/src/api/trustlens.js` | – | "Every request the website makes is in this one file" |
| **Website: results page** | `frontend/src/pages/Results.jsx` | – | "Shows score, summary, four checks, breakdown" |
| **Extension: reel audio (Whisper)** | `backend/browser_extension/gateway/reel_audio.py` | 332 (`transcribe`) | "Downloads the audio track and turns speech into text" |
| **Extension: how a reel is judged** | `backend/browser_extension/gateway/main.py` | 205 (`/analyze`) | "Gets the reel data, runs the same models as the website, builds the badge" |
| **Extension: the badge on Instagram** | `backend/browser_extension/extension/content.js` | – | "Draws the badge and the 'Scan this reel' button on the page" |

---

## Part 2 — The fake-follower files (the confusing part, sorted out)

There are many "fake follower" files. **Only these are used by the running app:**

| File | Used? | What it is |
|---|---|---|
| `backend/fake_follower.py` | ✅ **LIVE** | Runs on every scan. Builds features, asks the model |
| `backend/fake_follower_model.pkl` | ✅ **LIVE** | The trained Random Forest (95.8%) |
| `backend/train_fake_follower.py` | ✅ Training script | Re-creates the `.pkl` above. Run: `.\venv\Scripts\python.exe train_fake_follower.py` |
| `backend/archive/fake_follower_detection_ali/goyal-dataset/train.csv`, `test.csv` | ✅ **Training data** | Kaggle dataset: 576 train + 120 test accounts |
| `backend/fake_follower_graph/graph_cluster.py` | ✅ Offline method | Graph theory + Manhattan distance + Louvain |
| `backend/fake_follower_graph/run_analysis.py` | ✅ Offline method | Runs the graph method, prints the results, draws the picture |
| `backend/archive/fake_follower_detection_ali/master_dataset.csv` | ✅ Graph data | 1,890 accounts used by the graph method |

**NOT used by the app (explain if asked, don't open by mistake):**

| File | What it is | Why it's not used |
|---|---|---|
| `backend/fake_follower_model.broken-scaler-backup.pkl` | The **old, broken** model (said "genuine" for everyone) | Kept only as evidence of the bug we found and fixed |
| `backend/archive/fake_follower_detection_ali/*.py` (`app.py`, `train_models.py`, `predict_core.py`, `feature_engineering.py`, …) | **Ali's separate XGBoost model** (94.4%) with its own app | We keep **one** fake-account model live, so the website and extension can never give two different answers. Ali's work is the comparison showing RF, XGBoost and LSTM all score ~93–94% |
| `backend/archive/fake_follower_detection_ali/instafake-dataset-master/` | The raw InstaFake dataset | Already merged into `master_dataset.csv` |
| `backend/archive/misc/` | An old exploratory notebook | The source of the broken 99.3% model |

**One-sentence answer:** "The live model is `fake_follower.py` plus `fake_follower_model.pkl`, trained by `train_fake_follower.py` on the Kaggle data in `goyal-dataset`. The graph-theory method is in `fake_follower_graph`. Everything in `archive` is earlier or alternative work we compared against."

---

## Part 3 — The misinformation files, sorted out

| File / folder | What it is |
|---|---|
| `backend/misinfo_classifier/scripts/prepare_data.py` | **Step 1:** builds `unified_dataset.csv` from the 5 public datasets |
| `backend/misinfo_classifier/data/unified_dataset.csv` | **The dataset:** 46,392 texts, columns: text, category, label, source |
| `backend/misinfo_classifier/scripts/train_model.py` | **Step 2:** fine-tunes XLM-RoBERTa (run on Google Colab's free GPU) |
| `backend/misinfo_classifier/api/model/` | **The trained model:** `model.safetensors` (1.1 GB, not on GitHub), `config.json`, `tokenizer.json` |
| `backend/misinfo_classifier/api/model_loader.py` | **Step 3:** loads the model once and classifies text (`classify_text`) |
| `backend/misinfo_assessment.py` | **Step 4:** combines the AI's answer with the red-flag rules |
| `backend/red_flags.py` | The 12 scam-pattern rules (shared by the website and the extension) |
| `backend/misinfo_classifier/CoAID/`, `LIAR/`, `SMSSpam/`, `backend/datasets/` | Raw downloaded datasets (not on GitHub; public links in the Panel Guide) |

---

## Part 4 — Every backend file (`backend/`)

| File | What it does, in one line |
|---|---|
| `main.py` | **The front door of the backend.** Creates the FastAPI app, lists the web addresses (endpoints): sign-up, login, scan, history, reports. Loads the AI model at start-up |
| `scan_service.py` | **The scan pipeline:** fetch data → 4 checks → Trust Score → save |
| `data_ingestion.py` | Talks to RapidAPI to get Instagram profile, posts, captions, comments |
| `fake_follower.py` | Fake-account check (Random Forest) |
| `train_fake_follower.py` | Trains the fake-account model |
| `engagement_analyzer.py` | Engagement check + comment authenticity (rules) |
| `misinfo_assessment.py` | Misinformation check: AI + rules |
| `red_flags.py` | Scam-pattern rules |
| `credential_extractor.py` | Credential check (PMDC / US NPI registers) |
| `trust_score.py` | Combines the checks into the 0–100 Trust Score and verdict |
| `database.py` | Database tables + automatic backup on every start |
| `auth.py` | Password hashing, login tokens, "must be logged in" / "must be admin" checks |
| `email_service.py` | Sends the verification code (and watchlist alerts) through Gmail |
| `admin.py` | All admin console endpoints |
| `make_admin.py` | Command-line tool to make the first admin: `python make_admin.py you@example.com` |
| `watchlist.py` | Watchlist, alerts, daily automatic re-check |
| `insights.py` | PDF and CSV download endpoints |
| `reports.py` | Draws the PDF reports |
| `start.ps1` | **The start command:** `.\start.ps1` |
| `requirements.txt` | List of Python libraries to install on a new laptop |
| `.env` | **Secret keys** (RapidAPI, JWT, Gmail). Never shown or uploaded |
| `trustlens.db` | **The database file** (users, scans…). Never uploaded |
| `backups/` | Automatic database backups (last 14) |
| `tests/` | Automated tests: `test_scoring.py` (scoring rules), `test_account_api.py` (login/account), `test_dashboard_modules.py` (watchlist, PDF/CSV, comments-off) |
| `fake_follower_graph/` | Graph-theory fake-follower method (offline) |
| `misinfo_classifier/` | Misinformation model, training scripts, dataset |
| `browser_extension/` | Chrome extension + its gateway (below) |
| `archive/` | Old or set-aside work, **not used** (see `archive/README.md`) |

**Run the tests (to show they pass):**
```
cd backend
.\venv\Scripts\python.exe -m pytest tests -q
```

---

## Part 5 — The browser extension (`backend/browser_extension/`)

| File | What it does |
|---|---|
| `start_all.ps1` | Starts the extension's helper (and the backend if it isn't running) |
| **`extension/`** (loaded into Chrome) | |
| `extension/manifest.json` | Tells Chrome what the extension is and which sites it runs on (instagram.com) |
| `extension/content.js` | Draws the badge and "Scan this reel" button on Instagram |
| `extension/observer.js` | Notices when you scroll to a new reel |
| `extension/page_hook.js` | Reads the reel data Instagram's own page already loaded |
| `extension/instagram.js`, `parser.js` | Finds the post, the author and the caption on the page |
| `extension/api.js`, `background.js` | Send requests to the gateway |
| `extension/popup.html`, `popup.js` | The small window when you click the extension icon (green or red dots, settings) |
| `extension/state.js` | Saved settings |
| `demo.html`, `mock_test.html`, `preview_states.html`, `test_parser.*` | Test and preview pages (not part of the live extension) |
| **`gateway/`** (helper server, port 8100) | |
| `gateway/main.py` | The gateway's endpoints: `/analyze` (judge a reel), `/warm`, `/explain` |
| `gateway/instagram_data.py` | Gets reel and profile data (RapidAPI), with a cache |
| `gateway/reel_audio.py` | **Whisper**: downloads the audio and transcribes it |
| `gateway/scoring.py` | Uses the website's own Trust Score code for the badge |
| `gateway/analyzer.py` | Decides the badge colour and headline |
| `gateway/post_checker_api.py` | Serves the website's misinformation model to the extension |
| `gateway/follower_api.py` | Serves the website's fake-account model to the extension |
| `gateway/clients.py` | Connects the gateway to those two model services |
| `gateway/explain.py` | The "Why?" button text (Gemini, rules fallback) |
| `gateway/config.py`, `.env` | Settings; `.env` holds the Gemini key (secret) |
| `gateway/test_*.py` | 66 automated tests |

**How to load it in Chrome:** `chrome://extensions` → turn on **Developer mode** → **Load unpacked** → choose the folder `backend/browser_extension/extension`.

---

## Part 6 — The website (`frontend/src/`)

| File | What it is |
|---|---|
| `main.jsx` | The website's starting point |
| `App.jsx` | **The list of pages** (which web address shows which page) |
| `api/trustlens.js` | **Every call to the backend** |
| `context/AuthContext.jsx` | Remembers who is logged in |
| **Pages** (`pages/`) | |
| `Landing.jsx` | Home page |
| `Login.jsx`, `SignUp.jsx` | Log in / sign up (with email code) |
| `ScanPage.jsx` | Type a username; shows "scanning…" |
| `Results.jsx` | **The result page:** score, summary, four checks, breakdown, report button |
| `Dashboard.jsx` | Your scans, watchlist, alerts, reports, CSV export |
| `Comparison.jsx` | Compare 2–4 accounts, PDF/CSV |
| `About.jsx`, `Methodology.jsx`, `Extension.jsx` | Explanation pages (the Methodology page has the network picture) |
| `Settings.jsx` | Change name / password, delete account |
| `NotFound.jsx` | "Page not found" |
| `admin/` | The admin console (Overview, Users, Score reports, Scans, Models & system, Audit log) |
| **Components** (`components/`) | Reusable pieces |
| `ResultExtras.jsx` | The PDF download and Watch buttons on the Results page |
| `WatchlistPanel.jsx` | The watchlist and alerts on the Dashboard |
| `DisputePanel.jsx` | The "Report this score" box |
| `VerifyCodeForm.jsx` | The 6-digit email code box |
| `CountUp.jsx` | Numbers that count up when a page opens |
| `site/` | Navigation bar, footer, score ring, page layout |
| `styles/tl-kit.css`, `index.css` | The design (colours, fonts, buttons) |
| `lib/` | Small helpers (verdict colours, username checking, comparison colours) |

---

## Part 7 — The archive (NOT used by the app)

`backend/archive/`: say "this is earlier or alternative work, kept for reference".

| Folder | What's inside |
|---|---|
| `fake_follower_detection_ali/` | Ali's XGBoost fake-follower model and app, plus the datasets (**the datasets ARE used** for training and the graph method) |
| `video_to_text_transcriber_old/` | The first transcriber version (the extension now has its own Whisper) |
| `browser_extension/` | The old copy of the extension (the live one is `backend/browser_extension/`) |
| `account_roles/` | Creator and Brand dashboards: built, set aside for this demo, with a README on how to restore them |
| `charts_and_confidence/` | The Visual Analytics charts and the Trust Score confidence %: built, set aside for this demo, with a README on how to restore them |
| `misc/` | An old notebook (the source of the broken 99.3% model) |

---

## Part 8 — The three start commands

| Terminal | Command | What starts |
|---|---|---|
| 1 | `cd backend` then `.\start.ps1` | Backend at `http://127.0.0.1:8000` (API docs at `/docs`) |
| 2 | `cd frontend` then `npm run dev` | Website at `http://localhost:5173` |
| 3 | `cd backend\browser_extension` then `powershell -ExecutionPolicy Bypass -File start_all.ps1` | Extension helper at port 8100 |

**Nice trick to show the panel:** open `http://127.0.0.1:8000/docs`. FastAPI's automatic page lists every backend endpoint, and you can try them live.
