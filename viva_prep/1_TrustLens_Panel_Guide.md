# TrustLens — The Complete Panel Guide

*Everything about the project, told as a story, in plain words. Read sections 1–4 first (15 minutes). Use the rest as a reference when a question comes.*

**Final Year Project, BS Computer Science, Air University Islamabad (Faculty of Computing and AI)**
Hamza Qasim (231556) · Ali Ahmad (231667) · Umar Zubair (231601) · Supervisor: M. Zulfiqar Khan

---

## Contents

1. [The 60-second story (memorise this)](#1-the-60-second-story-memorise-this)
2. [The problem we are solving](#2-the-problem-we-are-solving)
3. [What the project is built with (the tech, in plain words)](#3-what-the-project-is-built-with-the-tech-in-plain-words)
4. [The journey of one scan: what happens in those 20 seconds](#4-the-journey-of-one-scan-what-happens-in-those-20-seconds)
5. [Every module, one by one](#5-every-module-one-by-one)
6. [How the Trust Score is calculated, and why those weights](#6-how-the-trust-score-is-calculated-and-why-those-weights)
7. [All datasets and research papers (with links)](#7-all-datasets-and-research-papers-with-links)
8. [The demo: what to show, in what order, what to say](#8-the-demo-what-to-show-in-what-order-what-to-say)
9. [Question bank: what the panel may ask, and your answer](#9-question-bank-what-the-panel-may-ask-and-your-answer)
10. [Honest limitations: say them before they catch you](#10-honest-limitations-say-them-before-they-catch-you)
11. [Numbers to remember (one-page card)](#11-numbers-to-remember-one-page-card)
12. [Start-up checklist for the demo](#12-start-up-checklist-for-the-demo)

---

## 1. The 60-second story (memorise this)

> "Every day people in Pakistan follow influencers who sell fake cures, fake investment schemes, or have bought thousands of fake followers. Pakistan loses billions of dollars a year to digital scams. An ordinary person has no way to check whether an influencer is genuine.
>
> **TrustLens** is our answer. You type an Instagram username, and in about 20 seconds TrustLens gives that account a **Trust Score from 0 to 100**, with a clear verdict: **Trusted**, **Moderate Risk** or **High Risk**.
>
> It gets there by running **four checks** on real, live Instagram data:
> 1. **Does the account itself look fake?** A trained machine-learning model.
> 2. **Is the engagement real?** Likes and comments compared with what is normal for an account of that size.
> 3. **Do the bio and posts spread misinformation or scams?** A trained language model that reads English and Urdu, double-checked by scam-detection rules.
> 4. **Are the credentials real?** If the bio says "Dr.", we check the official doctor registers.
>
> Every score comes with a full breakdown of how it was made, so nothing is a black box. There is also a **Chrome extension** that puts a trust badge on Instagram reels while you scroll, and it even **listens to the reel's audio**."

Say it slowly. That is your opening.

---

## 2. The problem we are solving

Three kinds of harm happen through influencers (all from our scope document):

| Problem | What it looks like | Which TrustLens check catches it |
|---|---|---|
| **Fake popularity** | Accounts buy followers and likes so they look big and trusted | Fake-account model + engagement check |
| **Misinformation and scams** | "This herb cures diabetes", "Guaranteed 300% returns" | Misinformation classifier + red-flag rules |
| **Fake experts** | Someone calls themselves "Dr." with no medical licence | Credential check against PMDC / US NPI registers |

**Why it matters in Pakistan (from the scope document's references):**

- Pakistan loses about **US $9.3 billion a year** to digital financial scams (Internews Pakistan / Global Anti-Scam report, ~2.5% of GDP).
- Over a thousand people were arrested over online fraud complaints in 2024 (ProPakistani).

**Who uses TrustLens:** ordinary people checking an account before they trust it, and (in the future) brands checking an influencer before paying them.

**What makes it different from HypeAuditor or Social Blade:** those tools are paid, built for marketers, and keep their formulas secret. TrustLens is free, **shows exactly how every score was made**, reads **Urdu**, checks **Pakistani doctor registrations (PMDC)**, and works **inside Instagram** through the extension.

---

## 3. What the project is built with (the tech, in plain words)

Think of TrustLens like a **restaurant**:

| Restaurant part | In TrustLens | What it actually is |
|---|---|---|
| The dining room the customer sees | **Frontend** (the website) | **React** (a JavaScript library for building web pages), started with **Vite** (a tool that runs the website on your laptop at `localhost:5173`) |
| The kitchen | **Backend** (the server) | **Python** with **FastAPI** (a framework for building web APIs). It runs on **Uvicorn** (the program that serves FastAPI) at `localhost:8000` |
| The waiter carrying orders | **API** | The website sends requests like "scan @nasa" to the backend and gets the answer back as JSON (structured text) |
| The pantry | **Database** | **SQLite**: one file, `backend/trustlens.db`. We talk to it through **SQLAlchemy** (a Python library, so we could switch to PostgreSQL later without rewriting code) |
| The suppliers | **Instagram data** | **RapidAPI's "Instagram Scraper Stable API"**, a paid service (Pro plan, 50,000 requests a month) that returns public profile, post and caption data |
| The chefs' special recipes | **AI models** | (1) **Random Forest** from **scikit-learn**, for fake accounts; (2) **XLM-RoBERTa** from **Hugging Face Transformers** (runs on **PyTorch**), for misinformation; (3) **Whisper** (**faster-whisper**), for turning reel audio into text |
| The security guard | **Login** | Passwords hashed with **bcrypt** (never stored in plain text); login tokens are **JWT** (a signed digital pass, valid 7 days); email verified with a 6-digit code sent through **Gmail** |
| The takeaway counter | **Browser extension** | A **Chrome extension (Manifest V3)**, plus a small helper server called the **gateway** (FastAPI, port `8100`) |
| The printed bill | **PDF reports** | **ReportLab** (a Python library that writes real PDF files) |
| The friendly waiter who explains the dish | **"Why?" explanations (extension)** | **Google Gemini** turns the extension's verdict into one plain-English sentence, **from our results only**. It never decides a score. If Gemini is down, our own rule-based sentence is used instead |

**One-line answer if asked "what is your backend?"**
> "The backend is Python, using the FastAPI framework, served by Uvicorn. It stores data in SQLite through SQLAlchemy, and the AI models are scikit-learn (Random Forest) and Hugging Face Transformers on PyTorch (XLM-RoBERTa)."

**Why these choices (if asked):**

- **FastAPI + Python:** every AI library (scikit-learn, PyTorch, Transformers, Whisper) is Python, so the models load straight into the web server. FastAPI is fast, and it generates API documentation automatically (open `http://127.0.0.1:8000/docs` to show it).
- **React:** the most widely used frontend library; the page updates without reloading.
- **SQLite:** zero setup, one file, perfect for a demo. Swapping in PostgreSQL only means changing one setting (`DATABASE_URL`).
- **RapidAPI instead of Instagram's official Graph API:** the official API only gives data about accounts that log in and grant permission, and it needs Meta's business verification and App Review. We need to analyse **any public** account, so a compliant third-party data provider was the practical choice.

---

## 4. The journey of one scan: what happens in those 20 seconds

Tell this as a story when you do the demo. Say "let me show you what happens behind the scenes".

**Step 1: You type `@nasa` and press Scan.**
The website (React) sends one request to the backend: *"scan nasa"*. You must be logged in; the backend checks your login pass (JWT) first.

**Step 2: The backend fetches the facts from Instagram (at the same time, to save time).**

- The **profile**: followers, following, number of posts, bio, profile picture, verified tick, link in bio.
- The **last 12 posts**: likes, comments and caption text of each.
- The **comments** on the newest post.

**Step 3: Four checks run.**

1. **Account authenticity:** the Random Forest looks at 16 facts about the profile and says how likely it is to be fake (e.g. "3%").
2. **Engagement:** average likes plus comments, divided by followers, compared with what is normal for that size of account.
3. **Misinformation:** the bio **and every one of the 12 captions** are read by XLM-RoBERTa, and each one is cross-checked against scam-pattern rules. The **riskiest** text decides this check, because one scam post is enough to matter.
4. **Credentials:** if the bio claims "Dr." or "MBBS", the name is looked up in the **PMDC** register (Pakistan) and the **US NPI** register.

**Step 4: The Trust Score is calculated.**
Each check gives a 0–100 score. They are combined with fixed weights (explained in section 6), giving one number from 0 to 100 and a verdict.

**Step 5: The result is saved and shown.**
It is saved in the database (so it appears on your Dashboard and can be reported), and the Results page shows the score, verdict, one-line summary, the four checks, the full breakdown, and a PDF download button.

**Where this whole journey lives in code:** one function, `analyze_username()` in `backend/scan_service.py`. Open that file if they ask to see "the pipeline".

---

## 5. Every module, one by one

The scope document lists **12 modules**. Here is the honest status of each, then the full story of each.

| # | Module | Status |
|---|---|---|
| 1 | Web Dashboard | ✅ Normal-user and Admin sides complete. 🟡 Creator and Brand dashboards: future work (built, then set aside to keep the demo focused) |
| 2 | Data Ingestion Pipeline | ✅ Done |
| 3 | Engagement Analyzer | ✅ Done |
| 4 | Fake Follower Detection | ✅ Done: two methods (live Random Forest + offline graph clustering) |
| 5 | Credential Extractor | ✅ Done: checks PMDC and US NPI registers |
| 6 | Misinformation Classifier | ✅ Done: XLM-RoBERTa, 77% accuracy, plus red-flag rules |
| 7 | Deepfake Scanner | ❌ Not in this version (explained below) |
| 8 | Trust Score Engine | ✅ Done: weights, kill switch, verdicts, reports/appeals (confidence % set aside) |
| 9 | Visual Analytics | ❌ Built, then set aside for this demo (future work) |
| 10 | Influencer Comparison Engine | 🟡 2–4 accounts, full metrics table, PDF + CSV (radar chart set aside) |
| 11 | Browser Extension | ✅ Done: Instagram (TikTok not supported) |
| 12 | Video-to-Text (Whisper) | ✅ Works inside the extension; 🟡 not yet in website scans |

**Overall: 7 modules fully done, 3 partly done, 2 not in this version: about **71%** of the scope ((7 full + 3 half) ÷ 12).** The supervisor's bar was 60%.

---

### Module 1 — Web Dashboard

**The story:** this is everything you see in the browser.

**Pages (all built in React):**

- **Landing page** (home): explains TrustLens, with a scan box.
- **Sign up / Log in:** a real account, email verified with a 6-digit code.
- **Scan page → Results page:** the main product.
- **Dashboard:** every scan you've run, a **watchlist** (accounts you keep an eye on, re-checked daily, with an alert if the score drops), your reports, and CSV export.
- **Compare:** 2 to 4 accounts side by side.
- **How it works, Methodology, Extension** pages.
- **Settings:** change name, password, or delete the account.
- **Admin console:** for admins only (below).

**Admin console (the scope's Admin role):**

| Scope says the admin does… | Where in TrustLens |
|---|---|
| Platform-wide analytics | Admin → Overview (scans per day, sign-ups, verdict split) |
| User account management | Admin → Users (search, suspend / reactivate, give admin rights) |
| Review disputed scores within 48 hours | Admin → Score reports (48-hour countdown, uphold with a corrected score, or reject) |
| Model performance monitoring | Admin → Models & system (the fake-account model is **re-tested live** on its test set every time the page opens: 95.8%) |
| Retraining feedback | Upheld reports export as a labelled CSV, the input for retraining |
| Audit log | Every admin action recorded with who, when and why |

**How reporting a score works:** a user who disagrees with a score presses **"Report this score"** on the Results page and writes why. It goes to the admin queue. The admin upholds or rejects it, and the user sees the decision on their Dashboard. **The original score is never overwritten**: the corrected one is stored next to it, because the difference is what we would retrain on.

**Security (if asked):**

- Passwords hashed with bcrypt.
- Login token (JWT) valid for 7 days.
- The email is verified once at sign-up. Say "email verification", **not** "2FA".
- The first admin can only be created from the command line (`make_admin.py`), not through the website.
- An admin cannot suspend themselves, and cannot judge a report they filed themselves.
- Every admin check happens on the **server**, not only by hiding buttons.

**Honest part:** the scope also describes a **Creator** dashboard and a **Brand** dashboard. We built both, then took them out of this version to keep the demo focused. Say: *"Those two roles are our next step; the code exists and is archived."*

---

### Module 2 — Data Ingestion Pipeline

**The story:** before we can judge an account, we need its facts. This module fetches them.

**How:** three calls to **RapidAPI's "Instagram Scraper Stable API"**:

1. **Profile:** followers, following, posts, bio, picture, verified, private, link.
2. **Last 12 posts:** likes, comments, caption, date of each.
3. **Comments on the newest post:** the actual comment text.

**Smart details worth mentioning:**

- Profile and posts are fetched **at the same time**, not one after the other, which makes scans faster.
- Every call has a **time limit** (20 seconds) and one automatic retry. Before this, one stalled request once hung a scan for 7 minutes.
- If the username doesn't exist, the user sees a clear message: "There's no public Instagram account called …".
- If the creator has **turned comments off**, we detect Instagram's own "comments disabled" marker and do **not** treat zero comments as a bot signal.

**Code:** `backend/data_ingestion.py`

**Why not Instagram's official API?** It only works for accounts that log in and give permission, and it needs Meta business verification and App Review. We need to check **any** public account.

**Honest part:** the endpoint for fetching an account's **follower list** is blocked. RapidAPI returns "Please try again later" every time (Instagram polices follower lists very strictly). That is why the graph-clustering method (Module 4b) runs offline.

---

### Module 3 — Engagement Analyzer

**The story:** bought followers don't like or comment. So an account with 1 million followers but only 200 likes per post is suspicious.

**How it works (rule-based, not AI):**

1. **Engagement rate** = (average likes + average comments) ÷ followers × 100.
   Example: 1,526 likes ÷ 419,361 followers = **0.36%**.

2. Compare it with what is **normal for that size**:

| Tier | Followers | Normal engagement |
|---|---|---|
| Nano | under 10k | 5% |
| Micro | 10k–100k | 3% |
| Macro | 100k–1M | 1.5% |
| Mega | over 1M | 0.8% |

3. Turn it into a 0–100 score on a **smooth curve** (no sudden jumps): at 0× normal the score is 5, at half of normal 35, at normal 65, at 1.5× normal 85, and at 2.5× normal 95.
4. **Comment authenticity:** reads real comments. If many are identical, that can be a bot or "comment pod". But if many different people write the same keyword ("link", "info"), that is a legitimate "comment X to get the link" campaign and is **not** flagged.
5. **Warnings** (shown, but they do not change the number): e.g. "Extremely low comments relative to likes", skipped when comments are turned off.

**Code:** `backend/engagement_analyzer.py` (`analyze_engagement`, `analyze_comment_authenticity`)

**Honest part:** the "normal" rates (5 / 3 / 1.5 / 0.8%) are **our own benchmarks**, based on common industry figures; they are not from one published source. Very big accounts (e.g. NASA) naturally have low engagement, so they can come out "Moderate Risk". Say it before they ask.

---

### Module 4 — Fake Follower Detection (two methods)

This is the module you'll be asked most about. **We have two different, real methods**, because they answer two different questions.

#### 4a. The live method: Random Forest (machine learning), runs on every scan

**The story:** we taught a computer what fake Instagram accounts look like by showing it hundreds of real examples, both fake and genuine. Now it looks at a new account and says how likely it is to be fake.

**What a Random Forest is (simple version):** imagine **200 people each making a checklist** ("no profile picture? very few posts? follows 3,000 people but only 20 follow back?"). Each person votes "fake" or "genuine", and the **majority vote** wins. Each "person" is a decision tree, trained on a slightly different sample of the data, so together they are more reliable than any one of them.

**The dataset:**

- **Name:** "Instagram fake spammer genuine accounts", public on Kaggle.
- **Link:** https://www.kaggle.com/datasets/free4ever1/instagram-fake-spammer-genuine-accounts
- **Size:** **696 accounts**, already split by the dataset's authors: **576 for training** (288 fake, 288 genuine) and **120 for testing** (60 fake, 60 genuine). Perfectly balanced, collected in March 2019 and labelled by hand.
- **Columns (12):** profile pic, nums/length username, fullname words, nums/length fullname, name==username, description length, external URL, private, #posts, #followers, #follows, fake (the label).
- **In the repo:** `backend/archive/fake_follower_detection_ali/goyal-dataset/train.csv` and `test.csv`

**The 16 features the model looks at:** the 11 facts above, plus 5 we calculate: follower-to-following ratio, posts per follower, has a bio, an engagement signal, and whether the username looks auto-generated.

**Result on the 120 accounts it never saw during training: 95.8% accuracy.**

- 58 fakes correctly caught and 57 genuine accounts correctly cleared.
- Only 3 genuine accounts wrongly called fake, and 2 fakes missed.

**How it was trained:** `backend/train_fake_follower.py`: 200 trees, fixed random seed (42) so anyone can reproduce it. It is trained on this laptop; the output is the file `backend/fake_follower_model.pkl`.

**Where it runs:** `backend/fake_follower.py` → `analyze_fake_followers()`

**The story of a bug we found (tell it; it shows honesty and skill):**
> "An earlier version claimed 99.3% accuracy. When we tested it properly, we found it said 'genuine' for **every single account**. The original training had scaled the numbers, but the saved model was fed unscaled numbers. So we retrained it properly: on a dataset that is in our repository, with a proper held-out test set. The honest result is 95.8%, and anyone can reproduce it."

**Important wording:** this model judges **the account itself**, not its followers. That's why the site says **"Account authenticity"** and **"fake-account likelihood"**.

**Honest limit:** a brand-new genuine account with very few posts can look fake to the model, because most "genuine" training examples were established accounts.

#### 4b. The method from the scope document: graph theory + Manhattan distance (runs offline)

**The story:** bot farms create hundreds of accounts **with the same script**, so they all look almost identical: no picture, digits in the name, empty bio, no posts. Real people are all different. So if we put all accounts on a map, the bots pile up on top of each other in tight clumps.

**How it works, step by step:**

1. **Measure how different every pair of accounts is**, using **Manhattan distance**. You add up the difference on each feature (like walking city blocks: 3 blocks east + 4 blocks north = 7).
   *Why Manhattan and not normal (Euclidean) distance?* Euclidean squares the differences, so one huge difference (like follower count) would drown out everything else. Manhattan keeps each feature fair. It is also what our scope document specifies.

2. **Draw a graph:** every account is a dot, and we connect two dots with a line if they are among the closest 1% of all pairs, i.e. they behave almost identically.
3. **Find the groups** with **Louvain community detection**, a standard graph algorithm that finds clusters that are densely connected inside. *Why Louvain and not k-means?* k-means needs to be told how many groups exist. We don't know how many bot farms there are; Louvain finds that out itself.
4. **Flag bot clusters:** a group of at least 5 accounts whose members carry the "mass-produced" fingerprint.

**Dataset:** `master_dataset.csv`, **1,890 real Instagram accounts** (1,342 genuine, 548 fake), 9 columns, combined from two public datasets:

- the Kaggle dataset above (696 accounts: 348 genuine, 348 fake)
- the **InstaFake** dataset by Akyon & Kalfaoglu (1,194 accounts: 994 genuine, 200 fake). Paper: https://arxiv.org/abs/1910.03090 · Data: https://github.com/fcakyon/instafake-dataset

**Results:**

| Measure | Result | In plain words |
|---|---|---|
| Precision | **94.7%** | When it says "bot farm", it's right 95% of the time |
| Recall | 38.9% | It finds about 4 in 10 fakes (only the ones that come in batches) |
| Accuracy | 81.6% | Overall correct calls |

Tested with 12 different settings: precision stayed between **94.6% and 99.2%** every time.

**Why recall is low (defend it confidently):** "Clustering can only catch bots that arrive in **batches**. A lone fake account has no twins to cluster with. That's exactly why we keep **both** methods: the Random Forest catches lone fakes, and the graph catches coordinated farms."

**The picture:** `backend/fake_follower_graph/follower_network.png` (also on the website's Methodology page). Bot farms show up as dense red knots. **This is a great slide to show.**

**Honest limit:** it runs **offline**, because the live follower-list endpoint is blocked (Module 2). The code (`cluster_accounts()`) accepts any list of accounts, so the day a follower list can be fetched, it runs on it unchanged.

**Code:** `backend/fake_follower_graph/graph_cluster.py`; run it with `run_analysis.py`.

**Papers for this module (from the scope document):**

- *Identification of Spambots and Fake Followers on Social Network via Interpretable AI-Based Machine Learning*, IEEE Access, vol. 13, 2025 (D. Javed, N. Z. Jhanjhi, et al.): https://ieeexplore.ieee.org/document/10929025/. This paper uses an interpretable machine-learning approach with engineered account features for spambot and fake-follower detection, the same idea as our Random Forest with readable features.
- *Detecting Influencer Authenticity on Social Media Platforms using Machine Learning and Natural Language Processing Techniques*, IJCSE: https://www.ijcscjournal.org/detecting-influencer-authenticity-social-media/

---

### Module 5 — Credential Extractor

**The story:** anyone can write "Dr." in their bio. We check whether a real, registered doctor has that name.

**How:**

1. **Find claims** in the bio with patterns (rule-based): MBBS, MD, "Dr.", PhD, CFA, CPA, Registered Dietitian, Licensed Therapist, Professor, and more. Short ones like "MD" only count in the right form, so "Mall Rd" isn't read as "Registered Dietitian" and "Md. Usman" isn't read as a doctor.
2. **Doctor claims are checked** in two official, free registers:
    - **PMDC** (Pakistan Medical & Dental Council), the same search box pmdc.pk offers the public.
    - **US NPI Registry** (US government): https://npiregistry.cms.hhs.gov/api-page
3. **Score:**
    - Found with an active licence: **90**. Several doctors share the name: **75**.
    - Found but licence inactive: **30**.
    - Not found in either register: **15**.
4. **Other claims** (PhD, CFA and so on) have no free public register, so they are **shown but not scored**.

**Code:** `backend/credential_extractor.py`

**Honest limit:** a match proves **a** registered doctor has that name, not that this Instagram account belongs to them.

**Why not Google search (as the scope doc says)?** Google's Custom Search API needed a billing account, and Google has closed it to new customers (it shuts down in January 2027). Official registers are more reliable than a web search anyway.

---

### Module 6 — Misinformation Classifier

**The story:** we trained a language model to read a caption and say whether it looks like misinformation or a scam, in English **and Urdu**.

**The model: XLM-RoBERTa (base).**

- A model from Facebook AI that has already read text in **100 languages**, including Urdu.
- We **fine-tuned** it: we taught it our specific task using our own dataset. Think of it as taking a student who already knows 100 languages and training them to be a fact-checker.
- **Why not GPT?** GPT is a paid, closed service; we can't train it on our data, and every scan would cost money and send data outside. XLM-RoBERTa runs on our own machine, for free, and reads Urdu.

**The 6 classes it chooses from:** credible, health misinformation, political propaganda, financial scam, sensational clickbait, Urdu misinformation.

**The dataset:** `backend/misinfo_classifier/data/unified_dataset.csv`, **46,392 rows**, 4 columns (text, category, label, source). It is built from 5 public datasets:

| Source dataset | Used for | Rows used | Link |
|---|---|---|---|
| **CoAID** (COVID-19 health misinformation) | health misinformation | 5,882 | https://github.com/cuilimeng/CoAID · paper: https://arxiv.org/abs/2006.00885 |
| **LIAR** (fact-checked political statements from PolitiFact) | political propaganda | 12,765 | https://www.cs.ucsb.edu/~william/data/liar_dataset.zip · paper: https://arxiv.org/abs/1705.00648 |
| **SMS Spam Collection** | financial scam (as a stand-in, since no Instagram-scam dataset exists) | 5,127 | https://archive.ics.uci.edu/dataset/228/sms+spam+collection |
| **FakeNewsNet** (GossipCop + PolitiFact headlines) | sensational clickbait | 21,724 | https://github.com/KaiDMML/FakeNewsNet · paper: https://arxiv.org/abs/1809.01286 |
| **UrduFake / "Bend the Truth"** (Urdu news, real and fake) | Urdu misinformation | 894 | https://github.com/MaazAmjad/Datasets-for-Urdu-news · paper: https://doi.org/10.3233/JIFS-179905 |

Of the 46,392 rows, **33,444 are credible examples** and **12,948 are misinformation or scam examples**.

**Training:** on **Google Colab** (free T4 GPU), with 4 epochs (4 passes over the data), learning rate 2e-5, batch size 16, and texts up to 384 tokens. The data was split **80% train / 10% validation / 10% test**. Rare classes were given more weight so the model didn't ignore them. Script: `backend/misinfo_classifier/scripts/train_model.py`.

**Result on the test set it never saw: 77% accuracy** (4,640 test texts).

| Class | How often it was right when it said this (precision) | How many of these it found (recall) |
|---|---|---|
| credible | 94% | 74% |
| health misinformation | 89% | 94% |
| political propaganda | 49% | 93% |
| financial scam | 92% | 95% |
| sensational clickbait | 60% | 77% |
| Urdu misinformation | 44% | 100% |

**Plain reading:** it almost never **misses** misinformation (high recall), but in some classes it raises false alarms (lower precision). That is why we added the rules below.

**The hybrid part (important, say it this way): "AI checked by rules".**

- We found the "financial scam" class had learned that **any promotion is a scam**, because SMS spam is mostly adverts. "Use my code for 10% off" was being flagged.
- So now a "scam" label **only counts if a concrete scam pattern backs it up**: guaranteed returns, "cures diabetes", "you have won a prize", disguised links, and so on. These are **12 kinds of red flags**, written as rules in `backend/red_flags.py`.
- If a hard red flag is found, it counts even if the AI said "credible".
- Other labels count in proportion to how often they were right on the test set (e.g. political propaganda counts 49%).
- **Result on our test captions:** false alarms on ordinary creator captions dropped from **8 of 20 to 0**, and real scams caught rose from **5 of 8 to 7 of 8**.
- **Live example to quote:** "This one root cures diabetes. Doctors hate this trick." The AI labelled it *political propaganda*, but the rule caught the health claim, so it was still correctly flagged.

**What it reads:** the bio **and all 12 recent captions**. The riskiest one decides the check.

**Code:**

- `backend/misinfo_classifier/api/model_loader.py` (runs the AI)
- `backend/misinfo_assessment.py` (AI + rules together)
- `backend/red_flags.py` (the rules)

**Honest limits:**

- Health misinformation was trained mostly on formal COVID news, so informal wellness scams may get the wrong sub-category (they are still flagged).
- The "financial scam" training data is SMS spam, a stand-in.
- The website scan reads captions, not reel audio (the extension does listen to audio).

---

### Module 7 — Deepfake Scanner (not in this version)

**What to say:**
> "Our teammate Ali built a prototype that checks profile pictures for AI-generated faces. We connected it, then decided to take it out of this version, because it hadn't been independently validated in our system and we didn't want an unverified model changing people's scores. It is future work, and the plan is to train it on the FaceForensics++ dataset as the scope describes."

**Paper (from scope):** Rössler et al., *FaceForensics++: Learning to Detect Manipulated Facial Images*, ICCV 2019: https://arxiv.org/abs/1901.08971

**Never** say it is working or "partly there".

---

### Module 8 — Trust Score Engine

Explained fully in [section 6](#6-how-the-trust-score-is-calculated-and-why-those-weights).

**In short:** four module scores combined with weights 25 / 20 / 25 / 10 (from the scope document), re-balanced so they always add up to 100% over the checks that actually ran.

- If the account is 85%+ likely fake, the score is capped at 15.
- Verdict: **70+ Trusted**, **40–69 Moderate Risk**, **below 40 High Risk**.
- A reviewer can correct a score through the "Report this score" flow; the original is never overwritten.

**Code:** `backend/trust_score.py`

**Honest part:** the scope's ethics section also asks for a **confidence %** on every score and a **"Requires further review"** label for scores 35–55. We built both, then set them aside for this demo; they're future work.

---

### Module 9 — Visual Analytics (set aside for this demo)

**What to say:**

> "We built this module: charts of the fake-account likelihood, each check's score, likes on each post and follower growth, each with a plain-language summary. Then we decided as a team to take it out of this version, so the demo stays focused on the core checks. The code is kept in our project's archive, ready to switch back on. It's future work."

The Results page still shows the Trust Score ring, the score scale and the four checks. Every number is still there, just not as extra charts.

**Never** say the charts are live.

---

### Module 10 — Influencer Comparison Engine

Compare **2 to 4 accounts** at once. The table shows every metric the scope asks for:

- Trust Score and verdict
- Bot % (fake-account likelihood)
- Misinformation flag count
- Engagement authenticity
- Comment authenticity
- Credential confidence
- Followers and posts

There's a **"Download PDF report"** and an **"Export CSV"** button. The best value in each row is marked "best". (The scope also asks for a radar chart; we built one and set it aside with the Visual Analytics charts.)

**Code:**

- `frontend/src/pages/Comparison.jsx`
- PDF: `backend/reports.py` → `comparison_pdf()`

---

### Module 11 — Browser Extension

**The story:** you don't want to leave Instagram to check someone. The extension puts a small **trust badge** on the reel or post you're looking at.

**How to use it:** open a reel and press **"Scan this reel"**.

- **Within about 1.5 seconds** you get the account and caption verdict. The full result, **including what was said in the audio**, takes about **4–8 seconds**.
- A reel you've already checked shows instantly.
- Colours: green (clean), yellow (caution), red (danger), grey ("not fully checked").

**How it works:**

- The extension reads the reel's data from the page, and a helper server (the **gateway**, port 8100) does the work.
- It uses **the same AI models as the website** (they share one copy in memory), so the extension and website can never disagree.
- It **listens to the audio** with **Whisper**, then checks the transcript for misinformation too.
- Press **"Why?"** for a plain-English explanation (Gemini, with a rule-based fallback).

**Honest rule we kept:** if the audio wasn't heard, the badge never shows a falsely green "all clear".

**Built by:** Ali Ahmad (original extension); rewired by us to use the project's own models.

**Honest limit:** Instagram only. The scope mentions TikTok; it isn't supported.

**Code:** `backend/browser_extension/extension/` (the Chrome part) and `backend/browser_extension/gateway/` (the helper server)

---

### Module 12 — Video-to-Text Transcriber (Whisper)

**The story:** scams are often **spoken** in reels, not written in captions. So we turn speech into text.

**How:** **faster-whisper** (a faster version of OpenAI's **Whisper**) with the "base" model, running on the laptop's CPU.

- It listens to the **first 45 seconds** of the reel.
- It downloads only the **audio track**, which is small and fast.
- It ignores music: if it isn't confident there's speech, the transcript is **shown but not scored**.

**Paper:** Radford et al., *Robust Speech Recognition via Large-Scale Weak Supervision* (OpenAI Whisper), 2022: https://arxiv.org/abs/2212.04356 · Library: https://github.com/SYSTRAN/faster-whisper

**Code:** `backend/browser_extension/gateway/reel_audio.py`

**Honest limit:** it works in the extension. Website scans read captions only.

---

## 6. How the Trust Score is calculated, and why those weights

### The formula (explain it like a school report card)

Each check gets a mark out of 100, and each check has a **weight** (how much it counts). The weights come from our scope document:

| Check | Weight | Score out of 100 |
|---|---|---|
| Account authenticity (fake-account model) | 25 | 100 − fake-account % |
| Engagement | 20 | the smooth curve from Module 3 |
| Misinformation | 25 | 100 − risk of the riskiest text |
| Credentials | 10 | the register result from Module 5 |

**If a check has nothing to check, it is left out and the others are re-balanced to 100%.** Example: no credential is claimed and there's no text, so only two checks apply. 25 + 20 = 45 becomes 55.6% and 44.4%.

- **Never a made-up number:** a missing check never gets a "neutral" placeholder score.
- All four apply: **31.25% / 25% / 31.25% / 12.5%**.
- No credential claim (most accounts): **35.7% / 28.6% / 35.7%**.

**Worked example (a real scan, @raisa.creationz):**

- Account 99.5 × 35.71% + Engagement 19.4 × 28.57% + Misinformation 99 × 35.72% = **76.4 → Trusted**.

**Kill switch:** if the account is **85% or more likely fake**, the score is capped at **15**. A fake account can't be trusted, however good its captions are.

**Verdict:** 70+ Trusted · 40–69 Moderate Risk · below 40 High Risk.

### "Why these weights? Is there a standard?" (the supervisor asked this; expect it)

**Honest answer:**
> "There is **no official standard**. Instagram publishes none, and commercial tools like HypeAuditor keep their formulas secret. Tools that do publish weights all use different ones (for example Phyllo uses 30/25/20/15/10). So we followed the recognised **method** for building a combined score: the **OECD/JRC Handbook on Constructing Composite Indicators** (2008). It says:
> 1. Put each indicator on the same scale: our 0–100.
> 2. Choose weights by **expert judgement**: ours are from the supervisor-approved scope document.
> 3. Combine them with a weighted average.
> 4. Handle missing data, which we do by re-balancing.
> 5. **Test sensitivity**, which we did."

**Our sensitivity test (on 33 real saved scans):**

| If we change the weights to… | Verdicts that changed |
|---|---|
| **All four checks weighted equally** | **0 of 33** |
| Any one weight 50% higher or lower | 0 to 4 of 33 |
| 500 random weight sets | 5.7% of cases, all scores sitting right next to a boundary |

> "So the verdicts come from the evidence, not from the exact weights we picked."

**Sources:**

- OECD/JRC Handbook: https://www.oecd.org/content/dam/oecd/en/publications/reports/2008/08/handbook-on-constructing-composite-indicators-methodology-and-user-guide_g1gh9301/9789264043466-en.pdf
- JRC record: https://publications.jrc.ec.europa.eu/repository/handle/JRC47008
- HypeAuditor (keeps its formula private): https://help.hypeauditor.com/en/articles/2221731-what-is-aqs-audience-quality-score-and-how-is-it-calculated
- Phyllo (publishes its own, different weights): https://www.getphyllo.com/post/influencer-audience-authenticity-score-how-to-build-one-with-social-data-apis

---

## 7. All datasets and research papers (with links)

### Datasets actually used

| Dataset | Module | Size | Link |
|---|---|---|---|
| Instagram fake spammer genuine accounts (Kaggle) | 4a Random Forest (train and test), 4b graph | 696 accounts (576 train + 120 test), 12 columns, balanced | https://www.kaggle.com/datasets/free4ever1/instagram-fake-spammer-genuine-accounts |
| InstaFake (Akyon & Kalfaoglu) | 4b graph clustering | 1,194 accounts used (994 genuine, 200 fake) | https://github.com/fcakyon/instafake-dataset |
| Combined `master_dataset.csv` | 4b graph clustering | 1,890 accounts, 9 columns (1,342 genuine, 548 fake) | built from the two above |
| CoAID | 6 health misinformation | 5,882 rows used | https://github.com/cuilimeng/CoAID |
| LIAR | 6 political propaganda | 12,765 rows used | https://www.cs.ucsb.edu/~william/data/liar_dataset.zip |
| SMS Spam Collection (UCI) | 6 financial scam | 5,127 rows used | https://archive.ics.uci.edu/dataset/228/sms+spam+collection |
| FakeNewsNet (headlines) | 6 clickbait | 21,724 rows used | https://github.com/KaiDMML/FakeNewsNet |
| UrduFake "Bend the Truth" | 6 Urdu misinformation | 894 rows used | https://github.com/MaazAmjad/Datasets-for-Urdu-news |
| Combined `unified_dataset.csv` | 6 | **46,392 rows**, 4 columns, 6 classes | built from the five above |

**Named in the scope document but not used (say why if asked):**

- **Cresci-2017 and TwiBot-22** are **Twitter** bot datasets. We used **Instagram** datasets instead, because our product analyses Instagram accounts and the features are different.
- **FaceForensics++** is for the deepfake module, which is future work.

### Research papers

| Paper | Used for | Link |
|---|---|---|
| Javed, Jhanjhi et al., *Identification of Spambots and Fake Followers on Social Network via Interpretable AI-Based ML*, IEEE Access vol. 13, 2025 | Module 4: interpretable feature-based fake-account detection (scope reference 5) | https://ieeexplore.ieee.org/document/10929025/ |
| *Detecting Influencer Authenticity on Social Media Platforms using ML and NLP*, IJCSE | Overall idea: ML + NLP for influencer authenticity (scope reference 4) | https://www.ijcscjournal.org/detecting-influencer-authenticity-social-media/ |
| Akyon & Kalfaoglu, *Instagram Fake and Automated Account Detection*, 2019 | Module 4 dataset (InstaFake) | https://arxiv.org/abs/1910.03090 |
| Breiman, *Random Forests*, Machine Learning 45, 2001 | Module 4a algorithm | https://doi.org/10.1023/A:1010933404324 |
| Blondel et al., *Fast unfolding of communities in large networks* (Louvain), 2008 | Module 4b algorithm | https://arxiv.org/abs/0803.0476 |
| Conneau et al., *Unsupervised Cross-lingual Representation Learning at Scale* (XLM-RoBERTa), ACL 2020 | Module 6 model | https://arxiv.org/abs/1911.02116 |
| Cui & Lee, *CoAID: COVID-19 Healthcare Misinformation Dataset*, 2020 | Module 6 data | https://arxiv.org/abs/2006.00885 |
| Wang, *"Liar, Liar Pants on Fire": A New Benchmark Dataset for Fake News Detection*, ACL 2017 | Module 6 data | https://arxiv.org/abs/1705.00648 |
| Shu et al., *FakeNewsNet*, Big Data 2020 (scope reference 8) | Module 6 data | https://arxiv.org/abs/1809.01286 |
| Amjad et al., *"Bend the Truth": Benchmark Dataset for Fake News Detection in Urdu*, JIFS 2020 | Module 6 data | https://doi.org/10.3233/JIFS-179905 |
| Almeida, Gómez Hidalgo & Yamakami, *Contributions to the Study of SMS Spam Filtering*, 2011 | Module 6 data | https://archive.ics.uci.edu/dataset/228/sms+spam+collection |
| Radford et al., *Robust Speech Recognition via Large-Scale Weak Supervision* (Whisper), 2022 (scope reference 7) | Module 12 | https://arxiv.org/abs/2212.04356 |
| Rössler et al., *FaceForensics++*, ICCV 2019 (scope reference 6) | Module 7 (future) | https://arxiv.org/abs/1901.08971 |
| OECD/JRC, *Handbook on Constructing Composite Indicators*, 2008 | Module 8: weights method | https://publications.jrc.ec.europa.eu/repository/handle/JRC47008 |

**Official services used:**

- PMDC doctor search: https://www.pmdc.pk
- US NPI Registry API: https://npiregistry.cms.hhs.gov/api-page
- RapidAPI Instagram Scraper Stable API (the Instagram data source)

---

## 8. The demo: what to show, in what order, what to say

**Total: about 10–12 minutes.** Practise it once.

| # | Show | Say (short) | Time |
|---|---|---|---|
| 1 | **Landing page** (`localhost:5173`) | The 60-second story from section 1 | 1 min |
| 2 | **Log in**, go to **Scan**, type a good account (e.g. `natgeo` or `cristiano`) | "Everything you'll see is live Instagram data, fetched right now" | 30 s |
| 3 | **Results page, top**: verdict, score ring, one-line summary | "One number and one plain sentence" | 1 min |
| 4 | Scroll: **the four checks** and **"Show the breakdown"** | "Nothing is a black box: every number and every weight" | 1 min |
| 5 | Press **Watch this account**, then open the **Dashboard** | "TrustLens re-checks watched accounts and alerts you if a score drops" | 1 min |
| 6 | **Download PDF report**, open it | "A real PDF a brand could take to a meeting" | 30 s |
| 7 | **Compare**: 3 accounts | "Side by side, every metric in one table, PDF report" | 1.5 min |
| 8 | **Methodology page**: the network picture | "Our graph-theory method: bot farms show up as red knots, 95% precision" | 1 min |
| 9 | **Extension**: open an Instagram reel and press **Scan this reel** | "It even listens to what's said in the reel" (**the wow moment**) | 2 min |
| 10 | **Admin console**: Overview, then Models & system (live 95.8%), then Score reports | "The admin can see the model being re-tested live, and review disputed scores within 48 hours" | 1.5 min |
| 11 | Close | "Two real ML models, honest rules around them, every score explained. Next: Creator and Brand dashboards, deepfake detection, TikTok" | 30 s |

**Wow points to say out loud:**

- "It reads **Urdu**."
- "It checks the **PMDC** register for fake doctors."
- "It **listens to reels**."
- "Every score has a full **breakdown**: every number and every weight."
- "We **caught our own model lying**: it said genuine for everyone, so we retrained it honestly. 95.8%, reproducible by anyone."
- "When our AI mislabelled 'this root cures diabetes' as political, our **rules still caught it**. That's why we built a hybrid."

**If something goes wrong in the demo (stay calm):**

- **A scan is slow or fails** (Instagram / RapidAPI hiccup): press Scan again, or open a scan you already ran from the **Dashboard**. Those open instantly, with no internet needed.
- **The extension shows "loading"**: models are still loading after start-up; wait 30 seconds.
- **The backend window closed**: run `.\start.ps1` again in the backend terminal. It takes about 20–60 seconds.
- **The panel types a fake username**: it correctly says "There's no public Instagram account called …". That's a feature; point it out.

**Good accounts to demo:** `natgeo`, `cristiano`, `leomessi`, `nasa`. Big accounts can show "Moderate Risk" because their engagement % is naturally low. **Explain it, don't hide it:** "For 100-million-follower accounts, 0.3% engagement is normal; our benchmark is strict, which is a known limitation."

---

## 9. Question bank: what the panel may ask, and your answer

### About the idea
**Q: What problem does TrustLens solve?**
People can't tell if an influencer is genuine. Fake followers, scams and fake experts cost Pakistan billions. TrustLens gives any public Instagram account a 0–100 Trust Score with a full explanation.

**Q: How is it different from HypeAuditor / Social Blade?**
Those are paid, built for marketers, and hide their formulas. TrustLens is free, explains every number, reads Urdu, checks PMDC, and works inside Instagram through the extension.

**Q: Who is it for?**
Ordinary users first, and brands and creators later (planned).

### About AI vs rules (they will push on this)
**Q: Which parts are real AI / machine learning?**
Two trained models: the **Random Forest** (fake accounts, 95.8%) and **XLM-RoBERTa** (misinformation, 77%). Whisper (speech to text) is a pre-trained model we use as-is. The rest (engagement, credentials, red flags, Trust Score) is **rule-based logic we designed**, and we say so on the website.

**Q: Isn't this just calling an API?**
No. RapidAPI only gives us the **raw facts** (followers, captions). Every judgement is made by our own trained models and our own rules, on our own machine.

**Q: Why Random Forest and not deep learning?**
The data is a small table of account facts (696 rows). On data like that, Random Forest is accurate, fast and explainable. Ali's comparison on 1,890 accounts found Random Forest 93.4%, XGBoost 94.4% and LSTM 93.7%: deep learning didn't help.

**Q: Why XLM-RoBERTa and not GPT / ChatGPT?**
It reads Urdu, runs free on our own machine, can be trained on our labelled data, and doesn't send users' data to a paid outside service.

**Q: What is fine-tuning?**
Taking a model that already understands language and training it further on our own examples, so it learns our specific task.

**Q: What does Gemini do? Isn't that an API doing the work?**
Only in the browser extension: when you press **"Why?"**, Gemini turns the badge's result into one plain-English sentence, from our results only. It never decides a score or verdict. If it's down, our own rule-based sentence is used instead.

### About accuracy and testing
**Q: How did you measure 95.8%?**
On **120 accounts the model never saw during training** (a held-out test set, split by the dataset's own authors): 115 correct out of 120. Anyone can reproduce it with `python train_fake_follower.py`. The admin page re-runs this test live.

**Q: Why is misinformation only 77%?**
It's a 6-way choice across very different kinds of text, in two languages. It rarely **misses** misinformation (high recall); its weakness is some false alarms, which is why the rule layer cross-checks it. On our caption tests that cut false alarms from 8 in 20 to 0.

**Q: How do you know the model isn't overfitting?**
Every number is measured on a **test set kept separate from training**. For the Random Forest, 95.8% on unseen data. We don't quote training accuracy.

**Q: The old model said 99.3%. What happened?**
We found it was broken: it said "genuine" for everyone, so it was really at chance (50%). We retrained it properly and now quote the honest 95.8%.

**Q: What are precision and recall?**

- **Precision:** when it says "fake", how often is it right?
- **Recall:** of all the fakes, how many did it find?

### About fake followers
**Q: Do you check the account's actual followers?**
The live model judges **the account itself**. Checking followers one by one needs the follower list, which Instagram blocks: the RapidAPI endpoint fails every time. So our follower-network method (graph theory + Manhattan distance) runs offline on a labelled pool of 1,890 real accounts, and the code is ready to run on live follower lists when they become available.

**Q: Explain Manhattan distance and Louvain.**

- **Manhattan distance:** add up the difference on each feature, like walking city blocks. It stops one big number drowning out the rest.
- **Louvain:** finds groups that are tightly connected, without being told how many groups exist.

**Q: Why is recall only 38.9%?**
Clustering only catches bots that come in batches. A lone fake has no twins. That's why we keep the Random Forest as well: the two methods cover each other's gaps.

### About the Trust Score
**Q: On what basis are the weights?**
See section 6: scope-document weights (expert judgement), following the OECD/JRC composite-indicator method, plus a sensitivity test where 0 of 33 verdicts changed with equal weights.

**Q: What if a check can't run?**
It's left out and the others are re-balanced to 100%. We never fill in a fake "neutral" number.

**Q: What if the score is wrong?**
The user presses "Report this score", and an admin reviews it within 48 hours. The corrected score is stored next to the original, never over it, as retraining data.

### About data, privacy and legality
**Q: Is it legal to use this data?**
We only use **public** profile data (anyone can see it without logging in), through a commercial data provider. We don't log into anyone's account, don't access private accounts, and only store scan results.

**Q: What personal data do you store?**
The user's name, email and hashed password, plus their scan results. Passwords are hashed with bcrypt. Secrets (API keys) are kept in a `.env` file that is never uploaded to GitHub.

**Q: What if Instagram changes its data format?**
All data fetching is in one file (`data_ingestion.py`), so only that file would change.

**Q: Is there a backup of the database?**
Yes. Every time the backend starts, it saves a dated copy (the last 14 are kept), and it can also copy to a second drive or Google Drive.

### About the tech
**Q: What's your backend?**
Python + FastAPI, served by Uvicorn. Database is SQLite via SQLAlchemy. Models are scikit-learn and Hugging Face Transformers (PyTorch).

**Q: How does the frontend talk to the backend?**
Through HTTP requests (a REST API) that exchange JSON. All of them are in one file: `frontend/src/api/trustlens.js`.

**Q: How does login work?**

- **Sign-up:** you register and get a 6-digit code by email. Entering it verifies the email once.
- **Log-in:** you get a signed token (JWT) valid for 7 days, and every request carries it.
- Passwords are stored as bcrypt hashes.

**Q: How long does a scan take?**
About 15–40 seconds, mostly waiting for Instagram's data. The AI part takes a few seconds.

**Q: Can it scale?**
The database can switch to PostgreSQL with one setting, and the models are loaded once and shared. For many users you would run several copies of the backend behind a load balancer and cache results. That's the plan for deployment.

**Q: How did you test it?**

- **56 backend and 66 extension automated tests** (scoring rules, logins, admin security, PDFs and more).
- Full click-throughs in a real browser.
- An independent re-calculation of every number on a real scan.

### About the team and the scope
**Q: Who did what?**

- **Hamza:** backend, AI integration and retraining, Trust Score, website, admin console, analytics.
- **Ali:** the browser extension, the first transcriber, a second fake-follower model (XGBoost) and a deepfake prototype.
- **Umar:** the comparison page and the original misinformation code.

**Q: The scope says 12 modules. How many are done?**
7 fully, 3 partly (the Dashboard's Creator/Brand roles, the Comparison radar chart, and audio only in the extension), and 2 not in this version (deepfake, and the Visual Analytics charts, which we built and set aside). The supervisor's bar was 60%; we're at about 71%.

**Q: What would you do next?**

- Creator and Brand dashboards (already built, being finalised)
- Visual Analytics charts and a confidence % on every score (both built, set aside for this demo)
- Deepfake detection trained on FaceForensics++
- TikTok support
- Reel audio in website scans
- Retraining misinformation on real Instagram scam data
- A mobile app

---

## 10. Honest limitations: say them before they catch you

Saying a limitation yourself looks professional. Being caught hiding one looks bad.

1. **Deepfake scanner** isn't in this version.
2. **Creator and Brand dashboards** are future work (built, set aside for this demo).
3. **The follower-network method runs offline**, because Instagram blocks follower lists.
4. **The fake-account model** can flag brand-new genuine accounts, because most "genuine" training examples were established accounts.
5. **Misinformation:**
    - The "financial scam" class was trained on SMS spam, a stand-in.
    - Health examples are mostly COVID news.
    - Accuracy is 77%.
6. **Engagement benchmarks** (5 / 3 / 1.5 / 0.8%) are our own. Very large accounts can come out "Moderate Risk".
7. **Credential check** proves a registered doctor has the name, not that it's the same person. Only doctors can be checked (no free register exists for PhD, CFA and so on).
8. **Website scans** read captions, not reel audio (the extension does both).
9. **Instagram only**: no TikTok yet.
10. **Visual Analytics charts and a confidence %** were built but set aside for this demo, so those scope items are future work.

---

## 11. Numbers to remember (one-page card)

| What | Number |
|---|---|
| Fake-account model accuracy (held-out) | **95.8%** (115 / 120) |
| Fake-account training data | 696 accounts (576 train / 120 test), 16 features, 200 trees |
| Graph method | 1,890 accounts · precision **94.7%** · recall 38.9% · accuracy 81.6% |
| Misinformation accuracy (held-out) | **77%** on 4,640 test texts |
| Misinformation dataset | **46,392** texts · 6 classes · 5 source datasets · English + Urdu |
| Red-flag rule types | 12 |
| Caption test | false alarms 8/20 → **0/20**; scams caught 5/8 → **7/8** |
| Weights | 25 / 20 / 25 / 10 → re-balanced to 100% |
| Verdict bands | 70+ Trusted · 40–69 Moderate · <40 High Risk |
| Kill switch | 85%+ fake → score capped at 15 |
| Sensitivity test | equal weights: **0 of 33** verdicts change |
| Scan time | ~15–40 s (mostly waiting for Instagram) |
| Extension | account + caption ~1.5 s; with audio ~4–8 s |
| Tests | 56 backend + 66 extension |
| Scope progress | 7 full + 3 partial + 2 not = ~71% |

---

## 12. Start-up checklist for the demo

Do this **30 minutes before**, not in front of the panel.

1. Open the project in VS Code. Open **three terminals** (Terminal → New Terminal).
2. **Terminal 1, backend:**
   ```
   cd backend
   .\start.ps1
   ```
   Wait until it says `Application startup complete` (20–60 seconds after a restart).

3. **Terminal 2, website:**
   ```
   cd frontend
   npm run dev
   ```
   Open `http://localhost:5173`.

4. **Terminal 3, extension helper:**
   ```
   cd backend\browser_extension
   powershell -ExecutionPolicy Bypass -File start_all.ps1
   ```
   It reuses the backend and opens one gateway window. Wait about 30 seconds.

5. In Chrome, check the extension popup: **all dots green**. Log into Instagram in that Chrome profile.
6. Log into TrustLens (a normal account, plus an admin account for the admin part).
7. **Run one test scan** (e.g. `natgeo`) so its result is ready on the Dashboard as a backup.
8. Keep this guide and the **Code Map** open in a second window.

**If PowerShell says "running scripts is disabled":** use `powershell -ExecutionPolicy Bypass -File start.ps1`. It's a Windows permission setting, not a bug.
