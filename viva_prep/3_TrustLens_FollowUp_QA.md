# TrustLens — Follow-Up Q&A (Auth, End Users, Model Choices, How the Models Talk)

*A short, focused companion to the main Panel Guide. Only four topics, explained in plain words, with the exact file and function to open if the panel says "show me". Every line number was checked against the real code today.*

---

## Contents

1. [Login and sign-up: how it actually works](#1-login-and-sign-up-how-it-actually-works)
2. [Who is the end user? (of the whole product, and of each module/page)](#2-who-is-the-end-user-of-the-whole-product-and-of-each-modulepage)
3. [Why THIS model and not another one?](#3-why-this-model-and-not-another-one)
4. [How do the different models talk to each other?](#4-how-do-the-different-models-talk-to-each-other)

---

## 1. Login and sign-up: how it actually works

**The one-sentence answer:** "We built our own login with email and password — not Google or Facebook sign-in. Passwords are scrambled with bcrypt so even we can't read them, and once you log in you're given a signed digital pass (a JWT) that proves who you are on every later request."

### The three files involved

| File | What it does |
|---|---|
| `backend/auth.py` | All the login *logic*: hashing, checking, creating the digital pass, checking who's logged in |
| `backend/main.py` (lines 194–302) | The three web addresses (endpoints) the website actually calls: `/signup`, `/login`, `/verify-email` |
| `backend/email_service.py` | Sends the 6-digit code by real email through Gmail |
| `backend/database.py` (line 30, the `User` table) | Where `password_hash` and `email_verified` are actually stored |
| `frontend/src/context/AuthContext.jsx` | The website's side: remembers who's logged in, saves the pass in the browser |

### Step by step: signing up

1. **You fill the sign-up form.** The website sends your name, email and password to `POST /signup` (`main.py:195`).
2. **The password is checked**, not stored, on the way in:
    - `auth.py`'s `password_strength_error()` (line 34) — at least 8 characters, with a letter **and** a number.
    - It must not be longer than 72 **bytes** — that's a hard limit of the bcrypt algorithm itself, not something we invented.
3. **The password is scrambled**, never saved as typed:
    - `auth.py`'s `hash_password()` (line 70) runs it through **bcrypt**, a one-way scrambling function built for passwords. "One-way" means there's no un-scramble button — not even we can turn a hash back into the real password. That scrambled text is what's saved in `database.py`'s `password_hash` column.
4. **The account is created with `email_verified = False`.** It exists, but can't log in yet.
5. **A 6-digit code is generated and emailed.** `auth.py`'s `generate_verification_code()` (line 27) makes a random 6-digit number using Python's `secrets` module — not the normal random-number generator, because `secrets` is the cryptographically-safe one, meant exactly for things like this. `email_service.py`'s `send_verification_code()` (line 31) sends it through a real Gmail account.
6. **The website shows the code-entry screen.** No login pass is given yet — you're not "in" until the code is confirmed.

### Step by step: confirming the code and logging in

1. You type the 6-digit code. The website calls `POST /verify-email` (`main.py:270`).
2. The backend checks: does this code exist for this email, is it unused, and has it not expired (10 minutes)? (`main.py:283–290`)
3. If it's right, `email_verified` is set to `True` **permanently** — this only ever has to happen once per account.
4. **A JWT (JSON Web Token) is created and handed back.** This is the "digital pass." `auth.py`'s `create_token()` (line 82) makes it: a small signed package saying "this is user #14, and this pass expires in 7 days." It's signed with a secret key (`JWT_SECRET`, stored only in `backend/.env`, never shown or uploaded).
5. **The website saves the token** in the browser (`localStorage`, `AuthContext.jsx`) and attaches it to every future request as an `Authorization: Bearer <token>` header.
6. **On every later request that needs to know who you are**, `auth.py`'s `get_current_user()` (line 104) reads that header, checks the signature is genuine and not expired, and looks up the matching user. If someone tampers with the token even slightly, the signature check fails and they're rejected.

### After that first time: plain password login

Once `email_verified` is `True`, `POST /login` (`main.py:236`) only ever needs the password — no code, ever again. That's the entire point of doing verification once at sign-up instead of every time.

**If someone never finished verifying** (closed the tab, etc.), `/login` checks the password first, then — instead of logging them in — sends them a **fresh** code and asks them to verify, so nobody gets permanently stuck.

### "Is this 2FA?"
**No, and this is a common trap question.** 2FA (two-factor authentication) means a code is required **every single time** you log in, forever. Ours asks for the code **once**, at sign-up, to prove the email is a real, reachable mailbox. After that, it's a completely normal password login. The correct name for what we built is **email verification**, and if asked, say that plainly rather than calling it 2FA.

### The security details worth quoting from memory

- Passwords: **bcrypt** hash, never stored or logged in plain text.
- Session pass: **JWT**, signed with `HS256`, valid **7 days**.
- Verification code: **6 digits**, generated with `secrets` (cryptographically safe), expires in **10 minutes**, stored in its own database table (`VerificationCode`), not in memory — so it survives a server restart.
- A **suspended account** is blocked on its *very next request*, even if its 7-day token hasn't expired yet (`auth.py:120`, checked on every request, not just at login).
- The **admin check** (`auth.py:128`, `require_admin`) happens on the server on every single admin request — hiding the "Admin" link in the menu for normal users is just cosmetic, not the real security.

---

## 2. Who is the end user? (of the whole product, and of each module/page)

**The one-sentence answer:** "TrustLens is free and built for anyone who follows influencers, but different parts of it are really aimed at different people — some checks matter more to an everyday follower, others matter more to a brand deciding who to pay."

### The whole product
Our scope document names three intended kinds of user (§10):

1. **Normal social media users** — anyone deciding whether to trust, follow, or buy from an account. This is the group the **current, fully-working version is built for**.
2. **Creators / influencers** — checking their own credibility score, proving it to brands. (This role was built and is set aside for now — future work, see the main guide.)
3. **Brands / agencies** — vetting influencers before paying them for sponsored posts. (Also built and set aside for now.)

**Say this plainly if asked:** "Right now, the live product's end user is the normal social-media user. The Creator and Brand roles exist in code but aren't switched on for this demo."

### Page by page — who actually uses each one

| Page | Who it's for |
|---|---|
| **Landing page** | Anyone, not even logged in — the "front door," explains what TrustLens is |
| **Sign up / Log in** | Anyone who wants their scans saved, or wants to report a score |
| **Scan page / Results page** | The core user: someone who typed a username because they want a straight answer — "can I trust this account?" |
| **Dashboard** (history, watchlist, alerts) | A **returning** user — someone who scans regularly and wants to keep an eye on accounts over time |
| **Comparison page** | Someone choosing **between** two or more accounts — e.g. "which of these two should I actually follow / buy from" (this is closest to the brand use case, even while used by a normal user) |
| **Admin console** | **Not a public user at all** — this is TrustLens's own staff: reviewing disputed scores, managing suspicious accounts, watching whether the AI models are still healthy |
| **Settings** | Any logged-in user managing their own account |
| **Browser extension** | Someone actively scrolling Instagram who wants a warning **in the moment**, without leaving the app |
| **About / Methodology pages** | A more skeptical reader — a journalist, a researcher, or (very relevantly) an exam panel — who wants to know *how* the score is really calculated |

### Module by module — who benefits from each check

| Module | Who cares most, and why |
|---|---|
| **Fake Follower Detection** | Normal users (don't want to trust a padded, bought-follower account) **and** brands (don't want to pay for reach that doesn't exist) |
| **Engagement Analyzer** | Mostly brands/marketers — "is this account's audience actually paying attention?" — but shown to every user |
| **Misinformation Classifier** | Normal users, especially anyone following health, finance or political content — protects them from being misled or scammed |
| **Credential Extractor** | Normal users being pitched by someone claiming to be "Dr." or a certified expert — protects against fake authority |
| **Trust Score Engine** | Everyone — it's the one number that summarises all the checks for whoever is reading the result |
| **Comparison Engine** | Brands and agencies specifically — this module's entire purpose in the scope document is pre-campaign vetting |
| **Admin console** | TrustLens's own team, not the public |
| **Browser extension** | Everyday Instagram scrollers, in real time |

---

## 3. Why THIS model and not another one?

This is one of the most common panel questions, and the honest answer is different for each of our three real machine-learning components — say so, rather than giving one blanket answer.

### 3a. Fake Follower Detection — why Random Forest?

**We genuinely did compare it against other models — this wasn't a guess.** Our teammate Ali trained and tested three different algorithms on the same 1,890-account dataset, held out a test set of 378 accounts none of them had seen, and measured all three honestly:

| Model | Accuracy | F1-score |
|---|---|---|
| Random Forest | 93.4% | 0.921 |
| **XGBoost** | **94.4%** | **0.933** |
| LSTM (a type of neural network / deep learning) | 93.7% | 0.924 |

**The honest finding: all three landed within one percentage point of each other.** That itself is informative — it tells you the *data* is the limiting factor, not the algorithm. With only 696–1,890 labelled accounts and 16–18 simple numeric features (followers, posts, bio length, and so on), there isn't enough data or complexity for a deep learning model like the LSTM to show any real advantage. Deep learning earns its reputation on large, complex data (images, long text, audio) — not on a small spreadsheet of numbers.

**So why did we ship Random Forest, not the slightly higher-scoring XGBoost?**

1. **Explainability.** A Random Forest's decisions can be read back as "which feature mattered how much" — useful for a project that promises to explain every score, not hide behind a black box.
2. **No feature scaling needed.** This is the most important reason, and it's personal to our project: **our original model was broken for months** because it was trained on scaled numbers but fed raw numbers at prediction time (see the main guide — it silently said "genuine" for every single account). A Random Forest splits data on plain thresholds and **never needs a scaler at all**, which permanently removes that entire class of bug. Choosing an algorithm that structurally can't repeat our own worst mistake was a deliberate, considered decision, not an accident.
3. **Fast and simple to retrain**, with a fixed random seed (42) so anyone — including the panel — can reproduce the exact same 95.8% result.

**Say this if pushed further:** "We didn't just pick the best-scoring number. We picked the model whose failure mode we understood, and whose specific weakness (needing a scaler) was exactly the bug that had already burned us once."

### 3b. Misinformation Classifier — why XLM-RoBERTa, and why not GPT/ChatGPT?

**Honest scope of what we compared:** unlike the fake-follower module, we did **not** train and compare several different architectures for this one — we picked XLM-RoBERTa from the outset, for clear, specific reasons, and only tuned the training data and process (see the main guide for the two failed Colab runs and the dataset composition fixes).

**Why XLM-RoBERTa specifically:**

1. **It already reads Urdu**, along with 99 other languages, out of the box. Our scope document requires Urdu support (for the Pakistani market); XLM-RoBERTa was trained from the start on a mix of 100 languages, so it comes with that ability built in — we only had to teach it *our specific task* (fine-tuning), not teach it Urdu from zero.
2. **We can fine-tune it on our own labelled data** and get a real, measurable, held-out accuracy number (77%). A model we can retrain and re-measure is defensible in front of a panel in a way a "trust me, it works" answer isn't.

**Why not GPT / ChatGPT, since it's the obvious alternative to bring up?**

1. **Cost per call.** GPT is a paid API — every single caption checked on every single scan would cost real money, for every user, forever. XLM-RoBERTa runs once, for free, on our own machine.
2. **Privacy.** Sending every scanned caption to an outside company's servers is a real data-handling question we didn't want to introduce.
3. **We can't fine-tune it on our labelled dataset** the way we can an open model — we'd be stuck with whatever general judgement GPT already has, with no way to specialise it for Instagram scam/misinformation patterns or measure its accuracy honestly on our own test set.
4. **Reliability and offline use.** A scan shouldn't fail because an external AI service is down, rate-limited, or has changed its API.

**Say this if pushed on "why not just use GPT for everything":** "GPT is genuinely stronger at open-ended reasoning, but we needed something we could fine-tune, measure, and run for free at scale — a smaller, specialised, trainable model was the right engineering choice for a classification task, not a creative one."

### 3c. Video-to-Text — why Whisper (specifically `faster-whisper`)?

1. **Free and open-source** — no per-minute cloud transcription cost.
2. **Runs locally** — the reel's audio never leaves the laptop.
3. **Genuinely strong on noisy, accented, and multilingual audio** — exactly the real-world condition of an Instagram reel (background music, code-switched Urdu/English speech), which is what it was built and marketed for.
4. **We use `faster-whisper`, a reimplementation of the same model that runs meaningfully faster on an ordinary CPU** — a real, practical concern, since we can't assume every laptop has a capable GPU (we hit exactly this limitation testing on this laptop specifically, see below).

**A real, honest example worth having ready:** we recently checked whether switching the extension's audio model from CPU to GPU would speed it up. On paper, yes — but when actually tested on this laptop, it failed with a missing CUDA library (`cublas64_12.dll`) that isn't installed here, even though the GPU itself is present. We chose not to make that change before the demo, because it would have **broken** audio transcription rather than sped it up, on this specific machine. That's a good, honest, technical story about engineering caution under time pressure, if it comes up.

---

## 4. How do the different models talk to each other?

**The one-sentence answer:** "They mostly *don't* talk to each other directly — each one works on its own and hands back a plain score. One piece of code, the Trust Score Engine, is the only thing that reads all of their answers and combines them. There is exactly **one** real exception, in the browser extension, where one model's output becomes another model's input."

### The honest architecture, in plain words

Picture four separate specialists, each examining the same patient (the Instagram account) for a different thing, and writing an independent report. Nobody consults anybody else — they each only see the raw case file (the account's data). Then **one manager** reads all four reports and writes the final verdict. That manager is `backend/trust_score.py`.

```
                     ┌─────────────────────────┐
   Instagram data ──▶│  Fake-account model      │──▶ bot_percentage (e.g. 3.0%)
   (from RapidAPI)    │  (Random Forest)         │
                     └─────────────────────────┘
                     ┌─────────────────────────┐
                    ▶│  Engagement Analyzer     │──▶ engagement_score (0-100)
                     │  (rules, no ML)          │
                     └─────────────────────────┘
                     ┌─────────────────────────┐
                    ▶│  Misinformation model    │──▶ risk_score per text
                     │  (XLM-RoBERTa + rules)   │
                     └─────────────────────────┘
                     ┌─────────────────────────┐
                    ▶│  Credential Extractor    │──▶ confidence_score (or none)
                     │  (rules + PMDC/NPI)      │
                     └─────────────────────────┘
                                  │
                                  ▼
                    trust_score.py: calculate_trust_score()
                       combines all 4 scores with weights
                                  │
                                  ▼
                         ONE Trust Score (0-100)
```

**Where this literally happens in code:** `backend/scan_service.py`, function `analyze_username()` (line 44). Read it top to bottom and you'll see exactly this: the fake-account check runs, then engagement, then credentials, then misinformation — **each one only ever reads the raw profile/post data that came from `data_ingestion.py`**, never another model's answer. Only at the very end does everything get handed to `calculate_trust_score()` in `trust_score.py` (line 43).

**Other code reads those same saved scores too, rather than recalculating them:**

- The **admin console**'s live model check and the **PDF report** both read the same saved scores — nothing is recalculated differently in different places.

### The one real exception: Whisper feeding XLM-RoBERTa

**This is the one place in the whole system where one trained model's output genuinely becomes another trained model's input**, and it only happens in the **browser extension**, on a reel:

1. **Whisper** listens to the reel's audio and produces a text transcript.
2. That transcript is added to the **same list of texts** (alongside the caption and bio) that get sent into the **misinformation classifier**.
3. XLM-RoBERTa then judges the transcript exactly like it would judge any caption — it has no idea the text came from speech rather than being typed.

**Where this happens in code:** `backend/browser_extension/gateway/main.py`, the `_combine()` function (line 398) and the `text_sources` list — the transcript text is simply added to the pile of texts the misinformation model reads.

**If asked "so do your models form a pipeline?"** — the accurate answer is: *"Mostly they're independent specialists feeding one combiner. The one genuine model-to-model pipeline we have is Whisper's transcript feeding into the misinformation classifier as another piece of text to judge."*

### Why we designed it this way (say this if asked "why not chain them more")

Keeping the four checks independent, rather than chaining them into each other, was a deliberate choice:

- **If one module fails or has nothing to check** (e.g. no bio text, or Instagram returns no posts), the others are unaffected — `trust_score.py` simply leaves that module out and re-balances the weights, instead of the whole pipeline breaking.
- **Each check stays independently testable and explainable.** If the panel asks "why did this account get flagged," we can point at exactly one module's report, not untangle a chain of models that influenced each other.
- **It matches how a human fact-checker would actually work** — look at several independent signals, then weigh them together, rather than letting an early, possibly wrong signal bias every later judgement.
