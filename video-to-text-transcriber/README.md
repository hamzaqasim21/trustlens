# Video-to-Text Transcriber

TrustLens Module 12. Takes an Instagram Reel — a link, an uploaded file, or a
stream URL handed over by the browser extension — pulls the audio out, runs
Whisper over it, and hands back Urdu or English text the Misinformation
Classifier can actually use.

Runs entirely on your own machine. Nothing here calls a paid API.

---

## Getting it running

This module is self-contained. From the repository root:

```bash
cd video-to-text-transcriber
```

then:

```bash
python -m venv .venv
```
```bash
.venv\Scripts\activate
```
```bash
pip install -r requirements.txt
```
```bash
python run.py
```

That's the whole setup. Open <http://127.0.0.1:8000> for the demo page, `/docs`
for the API.

If something looks wrong, this tells you what and how to fix it:

```bash
python scripts/doctor.py
```

Two things worth knowing up front:

- **You don't need to install FFmpeg.** `imageio-ffmpeg` ships a static build and
  we find it automatically. If you already have FFmpeg on PATH we'll use that
  instead, since it's usually newer.
- **First run pulls the Whisper weights** (~480 MB for `small`) into
  `data/models/`. One time only; after that it's fully offline.

---

## Why the tech stack differs from the scope document

The scope document specifies Whisper large-v3 via OpenAI's `openai-whisper`
package. We run the same model on a different runtime: **faster-whisper**, which
executes identical Whisper weights on CTranslate2 instead of PyTorch.

This wasn't a preference. On the dev laptop (i5-7200U, 2 cores, no GPU) the
reference runtime takes several minutes for a 30-second reel — you can't demo
that, let alone batch it. faster-whisper does the same work roughly 4× faster at
about half the memory, and int8 quantisation is what makes large models fit on a
CPU box at all. Same checkpoints, same architecture, same output, so the accuracy
claims in the proposal still stand.

Everything else in the scope document held up: yt-dlp, FFmpeg, FastAPI,
PostgreSQL. Database access goes through SQLAlchemy so it's SQLite while you're
developing and PostgreSQL in production, with `DATABASE_URL` the only difference.

### One clarification, because it matters for the "free" requirement

"OpenAI Whisper" refers to two different things and people conflate them:

- The **hosted Whisper API**, billed per minute. We don't touch it.
- The **Whisper model**, MIT-licensed, downloads once, runs locally. That's what
  this uses.

---

## The parts that took actual work

Wrapping Whisper in an HTTP endpoint is an afternoon. These three are where the
time went, and they're the reason the output is usable downstream.

### Urdu kept coming out as Hindi

Urdu and Hindi are the same spoken language written in two scripts, and Whisper's
training data skews heavily Hindi. Feed it Pakistani Urdu and it will often tag
the language `hi` and write the transcript in **Devanagari**.

That's fatal for us, not cosmetic — the classifier is trained on Urdu Arabic
script, so a Devanagari transcript tokenises into noise. It's also the kind of
bug that doesn't announce itself: you get fluent, confident-looking text in the
wrong alphabet.

Three defences, because no single one was reliable:

- **Detection.** Probe several VAD-selected windows and vote instead of trusting
  the first few seconds — reels often open with a music sting or an English hook
  before the Urdu starts. Then, if Whisper says Hindi but Urdu also scores
  plausibly, take Urdu. We're analysing Pakistani accounts; `hi` on Hindustani
  speech is far more likely to be a training artefact than a real Hindi speaker.
  Genuine Hindi (high `hi`, negligible `ur`) passes through untouched.
- **Decoding.** Prime the decoder with a short Urdu-script `initial_prompt`, which
  pulls its output distribution toward Urdu orthography.
- **Repair.** If Devanagari still shows up, transliterate it back and flag that we
  did, so nobody downstream mistakes a converted transcript for a native one.

Toggle with `URDU_BIAS_ENABLED=false` if you want to see what Whisper says
unaided — useful when you're measuring how often the correction actually fires.

### Whisper makes things up over music

Point Whisper at a stretch of music with no speech and it will confidently write
"Thanks for watching!" or "Subtitles by the Amara.org community". It learned that
from scraped YouTube subtitles. It also gets stuck in loops, repeating one phrase
until the segment ends.

For a misinformation classifier this is worse than silence, because nothing
downstream can tell invented text from real text. So we filter before anything
leaves this module: known boilerplate phrases, repetition loops (word-level
n-gram analysis), low-entropy segments, duplicate neighbours, and segments
Whisper itself scores as silence.

The single biggest win was turning **off** `condition_on_previous_text`. Letting
Whisper condition on its own prior output is what drives the runaway repetition
on short musical clips.

Every dropped segment is reported with its reason. Nothing disappears quietly —
if the filter is wrong you can see that it was wrong.

### Confidence had to mean something

The scope document promises a confidence indicator but doesn't say what it is, and
an arbitrary number would be worse than none.

`exp(avg_logprob)` is the geometric-mean token probability — a real quantity
Whisper already computes — scaled by `(1 - no_speech_prob)` so a segment the model
thinks is silence can't score high, then duration-weighted across segments so a
long clear passage outweighs a half-second mumble. That's what lets the Trust
Score Engine discount weak evidence instead of treating every transcript as equal.

---

## API

Everything under `/api/v1`.

| Method | Endpoint | |
|---|---|---|
| POST | `/transcribe/url` | Instagram link (TikTok works too) |
| POST | `/transcribe/upload` | A file |
| POST | `/transcribe/direct` | A CDN URL the extension already resolved |
| POST | `/transcribe/raw` | Synchronous ASR on prepared audio — the GPU worker contract |
| GET | `/jobs/{id}` | Poll |
| GET | `/jobs/{id}/stream` | Live progress over SSE |
| GET | `/health` | Readiness and capabilities |

Transcription is asynchronous — you get a `job_id` back immediately and poll or
subscribe. On a CPU box a job takes tens of seconds, which is far too long to hold
a request open. Pass `"wait": true` if you'd rather block and take it in one round
trip.

### What the classifier consumes

`classifier_input` is the contract between this module and the next one:

```json
{
  "classifier_input": {
    "text": "…transcript, plus OCR text when speech was weak…",
    "language": "ur",
    "sources": ["speech", "on_screen_text"],
    "confidence": 0.83,
    "quality": "good",
    "is_reliable": true,
    "chunk_count": 2,
    "chunks": [ … ]
  }
}
```

Gate on `is_reliable` and `confidence`. Everything else in the response is
provenance for debugging.

**Read `chunks`, not `text`, for anything over about 90 seconds.** See below.

### Long videos and the 512-token wall

XLM-RoBERTa caps at 512 tokens and **truncates silently** past that — no
exception, no warning. A three-minute reel comes out around 720 tokens in English
and more in Urdu, since XLM-R's SentencePiece vocabulary fragments Urdu into more
pieces per word.

Hand that over unchunked and the classifier never sees the last third of the
video. A scam claim in the final thirty seconds would be invisible while the
verdict still looked confident. That's the worst failure mode available to a
system whose whole job is trustworthy verdicts.

So the transcript arrives pre-cut into windows, done here where the timestamps and
per-segment confidences still exist to attach:

```json
"chunks": [
  { "index": 0, "start": 0.0,  "end": 122.1, "est_tokens": 474, "confidence": 0.76, "text": "…" },
  { "index": 1, "start": 95.0, "end": 190.0, "est_tokens": 322, "confidence": 0.76, "text": "…",
    "is_overlap_continuation": true }
]
```

What you can rely on:

- Every window fits. The cap is 480, leaving headroom under 512 for special
  tokens. A single over-long segment gets split on word boundaries rather than
  allowed to overflow.
- Windows overlap by ~64 tokens, so a claim sitting on a seam survives intact in
  at least one of them.
- Timestamps and confidence per chunk, so a flagged chunk points at a moment in
  the video and can be weighted by how well that stretch was heard.
- The last chunk always reaches the end. No silent tail loss.

Classify each chunk and take the **max** risk across them, weighted by
confidence — one false claim makes the video misinformation, and averaging would
dilute it away. When `chunk_count == 1`, `chunks[0].text` equals `text`, so one
code path handles both.

### If you're building the extension

`POST /api/v1/transcribe/direct` is ready for you:

```json
{ "media_url": "https://…cdninstagram.com/….mp4",
  "page_url":  "https://www.instagram.com/reel/…/",
  "headers":   { "Referer": "https://www.instagram.com/" } }
```

Two things that will cost you an afternoon if nobody tells you:

- Instagram plays most reels through Media Source Extensions, so the `<video>`
  element's `src` is a **`blob:` URL**. Blobs only exist inside that page — the
  server can't fetch one. Grab the real CDN URL from the network layer
  (`chrome.webRequest`, observation-only under MV3). The endpoint rejects `blob:`
  with an explanation rather than a confusing failure.
- Don't forward cookies or auth headers. We only need the media bytes, and
  `Referer` is enough. Keep the session on your side.

---

## Speed, and what to do about it

On the dev laptop (i5-7200U, 2 cores, no GPU) with `small` + int8:

| Clip | Time |
|---|---|
| 30 s reel | ~20 s |
| 190 s | ~140 s (1.6× realtime) |
| 10 min | ~6–7 min |

In order of how much they buy you:

1. **Free Colab T4** — by a wide margin. Runs `large-v3` faster than this laptop
   runs `small`, with better Urdu. Setup below.
2. `ASR_BEAM_SIZE=1` — greedy decoding, ~1.5–2× faster for a small accuracy cost.
   Fine for bulk pre-processing.
3. `ASR_MODEL=base` — ~2.5× faster than `small`, but Urdu accuracy falls off a
   cliff. English only.
4. Leave VAD on (it is by default). Skipping music and silence before the decoder
   sees them is both a speed and an accuracy win on reels.

`MAX_DURATION_SEC` caps input at 900 s. Raise it if you need to, but a 30-minute
video on CPU is a 20-minute job — use the GPU.

---

## Running the heavy model on a free Colab T4

Your laptop still does everything except the Whisper decode: fetching the reel,
extracting audio, filtering, chunking. Only the expensive part moves.

Bundle the code:

```bash
python scripts/make_colab_bundle.py
```

Upload `colab/TrustLens_GPU_Worker.ipynb` to Colab, set
`Runtime → Change runtime type → T4 GPU`, and run the cells. They install
dependencies, take your zip, preload `large-v3`, benchmark the GPU, start the
server and open a Cloudflare tunnel. The last cell prints what to paste locally:

```bash
ASR_BACKEND=remote
```
```bash
REMOTE_ASR_URL=https://something-random.trycloudflare.com
```

Restart `python run.py` and you're on the GPU.

The notebook uploads *your* `app/` package rather than running a hand-written
mini-server, so the worker applies the same language policy and the same
hallucination filter. A second implementation would drift from local results and
you'd lose days finding out why.

Things to expect:

- **The URL changes every session.** Free Colab stops after ~90 min idle or ~12 h
  total. Re-run, paste the new URL. Don't hardcode it.
- **The ~3 GB model download repeats each session.** Colab caches nothing between
  sessions.
- **The tunnel is public while it runs** — a random hostname that dies with the
  notebook. Fine for development. Don't post it; set `WORKER_TOKEN` /
  `REMOTE_ASR_TOKEN` if you want a shared secret.
- **Failures are loud.** An unreachable worker raises `Remote ASR call failed`
  rather than silently dropping to CPU, so a dead tunnel can't masquerade as a
  working one. `ASR_BACKEND=local` puts you back on the laptop.

---

## Instagram links need cookies

File upload works with no setup at all. Pasting a **URL** doesn't, because
Instagram refuses anonymous downloads.

```bash
python scripts/setup_cookies.py
```

It works out which method will succeed on your machine. Two traps it checks for:

- **Chrome has to be fully quit** before yt-dlp can copy its cookie database,
  and Chrome leaves background processes behind — check Task Manager. Otherwise
  you get `Could not copy Chrome cookie database`.
- **Edge doesn't work at all** on current Windows builds. App-Bound Encryption
  fails with `Failed to decrypt with DPAPI` and quitting Edge doesn't help.

The `cookies.txt` route sidesteps both and doesn't need you to close anything.
Install "Get cookies.txt LOCALLY", go to instagram.com logged in, and export
**for that site only** in Netscape format. Save it as `cookies.txt` in the project
root — it's picked up automatically, no `.env` edit.

> **Export the site, not the browser.** "Export all cookies" dumps every session
> you have open — email, banking, everything — into one plaintext file sitting in
> a project directory. If you've already done that,
> `python scripts/strip_cookies.py` reduces it to the domains this project needs.

`cookies.txt` is a live key to your account. It's gitignored, but keep it out of
submissions and shared folders, and re-export if you ever hand the project to
someone.

Sessions expire after a few weeks. When URL fetching suddenly breaks, that's
usually why — `scripts/doctor.py` will tell you.

---

## Configuration

`.env.example` → `.env`. Everything has a working default; an empty `.env` runs.

| Variable | Default | When you'd change it |
|---|---|---|
| `ASR_MODEL` | `small` | `medium` / `large-v3` for better Urdu, given the compute |
| `URDU_BIAS_ENABLED` | `true` | `false` to see Whisper's unaided language call |
| `AUDIO_DENOISE` | `light` | `aggressive` for reels with very loud music |
| `OCR_ENABLED` | `false` | `true` to read burned-in on-screen text |
| `DATABASE_URL` | SQLite | Point at PostgreSQL for production |
| `ASR_BACKEND` | `local` | `remote` to use the Colab GPU worker |

On denoising: it's deliberately light. Whisper was trained on messy real-world
audio and is already robust to noise — aggressive filtering strips formants and
measurably *hurts* accuracy. The default chain only band-limits to the speech
range and evens out levels so quiet speech isn't buried under loud music.

---

## Tests

```bash
python -m pytest tests/ -q
```

64 tests over the Urdu/Hindi decision, script repair, code-switching detection,
hallucination filtering, confidence maths, and chunk packing. No audio, no
network, runs in under a second.

Against a real file or URL:

```bash
python scripts/smoke_test.py path\to\video.mp4
```

The chunking tests are worth keeping green. One of them caught a case where an
over-long segment was packed into a window that exceeded the classifier limit
with no warning — the exact silent-truncation failure the chunker exists to
prevent.

---

## Known limitations

Read these before demoing.

- **Urdu is not yet verified end-to-end on real audio.** The language decision and
  script repair are unit-tested, and the full pipeline is verified on English, but
  no Urdu speech sample has been run through it here. Do that before the panel —
  an Instagram reel upload is the quickest check.
- **Urdu accuracy is genuinely below English.** Whisper's Urdu word error rate is
  several times its English rate, and the gap widens with background music and
  code-switching. That's the reason confidence scoring exists rather than being
  decoration. `medium` and `large-v3` narrow it considerably.
- **Keep yt-dlp updated.** Instagram changes its defences constantly and a stale
  yt-dlp fails with `Requested format is not available`, which looks like a bug in
  this project but isn't. It's intentionally unpinned in `requirements.txt`. When
  URL downloads break: `pip install -U yt-dlp`.
- **Prefer file upload for a live demo.** URL fetching works, but it depends on
  unexpired cookies and Instagram not having changed anything that morning.
  Upload has no moving parts.

---

## Layout

```
app/
  config.py            env-driven settings
  main.py              FastAPI app
  jobs.py              async queue + worker pool
  db.py                SQLAlchemy models, cache, stats
  schemas.py           request/response models
  api/routes.py        endpoints
  pipeline/
    acquire.py         yt-dlp / upload / direct CDN
    audio.py           FFmpeg conditioning, frame sampling
    asr.py             faster-whisper engine, language detection
    language.py        Urdu/Hindi policy, script repair
    postprocess.py     hallucination filter, confidence
    chunking.py        512-token windows for the classifier
    ocr.py             on-screen text fallback
    orchestrator.py    stage wiring
web/index.html         demo UI
colab/                 GPU worker notebook
scripts/               doctor, cookie setup, smoke test, bundler
tests/                 64 unit tests
```

On the job queue: it's an asyncio queue plus a bounded thread pool, not Celery
and Redis. Celery is the textbook answer, but it means running a broker and a
separate worker process for what is a handful of jobs at a time on one machine.
The `submit` / `get` / `subscribe` surface is small enough that swapping Celery in
behind it later is a contained change. Worker concurrency defaults to 1 on
purpose — Whisper already saturates every core it's given, so two jobs at once on
a 2-core laptop makes both slower than running them in sequence.

---

TrustLens · Air University Islamabad · FCAI · 2025-26
