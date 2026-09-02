# Running Whisper on a free Colab GPU

Whisper on this laptop is the slowest part of the pipeline by a wide margin.
Moving just the transcription step onto a free Colab T4 fixes two things at once:

| | Laptop CPU | Colab T4 |
|---|---|---|
| 56-second reel | 371s (about 6x realtime) | seconds |
| Whisper model | `small` | `large-v3` |
| Urdu confidence | 0.39, flagged unreliable | noticeably better |

Cost is nothing: free Colab, free Cloudflare tunnel, no card, no signup beyond a
Google account.

## Why it helps this much

Whisper is doing a lot of matrix multiplication. The laptop has two cores, and
right now Whisper is also competing with the 1 GB misinformation model for them. A
T4 has 2,560 CUDA cores and is doing nothing else.

The bigger win is the model size. We run `small` locally only because `large-v3`
is unusable on CPU. On a T4, `large-v3` finishes faster than `small` does here, so
this isn't "the same answer sooner", it's a better answer sooner. Whisper's Urdu
accuracy mostly lives in the larger models.

What stays local: downloading the reel (so `cookies.txt` never leaves the
machine), audio extraction, hallucination filtering, chunking, confidence scoring.
Only the Whisper decode moves. The architecture is unchanged, one stage just runs
somewhere else.

## Setup

### 1. Bundle the code

```bash
cd "D:\video-to-text transcriber" && .venv\Scripts\python.exe scripts\make_colab_bundle.py
```

That writes `colab_bundle.zip`, about 46 KB, containing the `app/` package.

The notebook uploads our own code rather than running a hand-written mini server,
so the GPU applies the same Urdu language policy and hallucination filter as the
laptop. A separate implementation would quietly produce different results, which
is a nasty thing to discover during evaluation.

### 2. Open the notebook in Colab

Upload `D:\video-to-text transcriber\colab\TrustLens_GPU_Worker.ipynb` to
<https://colab.research.google.com>.

Then set Runtime → Change runtime type → T4 GPU, *before* running anything. That
restarts the machine, so doing it later means starting over.

### 3. Run the cells

They install dependencies, take the zip upload, preload `large-v3`, benchmark the
GPU, start the server and open a Cloudflare tunnel. The last cell prints a URL:

```
https://something-random-words.trycloudflare.com
```

### 4. Point the laptop at it

```bash
cd "D:\video-to-text transcriber" && .venv\Scripts\python.exe scripts\use_gpu.py https://something-random-words.trycloudflare.com
```

This checks the worker is alive and is actually a TrustLens worker before writing
anything, so a typo or a dead tunnel fails in two seconds instead of halfway
through a transcription. It also warns if the worker reports `cpu` instead of
`cuda`, which means the T4 setting in step 2 didn't take.

### 5. Restart the transcriber

```bash
cd "D:\video-to-text transcriber" && .venv\Scripts\python.exe run.py
```

That's the whole switch. The extension needs no changes: it talks to the gateway,
the gateway talks to the transcriber, and only the transcriber's ASR stage moved.

## Switching back

```bash
cd "D:\video-to-text transcriber" && .venv\Scripts\python.exe scripts\use_gpu.py --local
```

To check what's currently set and whether the worker is still alive:

```bash
cd "D:\video-to-text transcriber" && .venv\Scripts\python.exe scripts\use_gpu.py --status
```

## Things to expect

The URL changes every session. Free Colab stops after roughly 90 minutes idle or
12 hours total, and the tunnel dies with it. Re-run the notebook, then re-run
`use_gpu.py` with the new URL. That's the main reason the script validates instead
of trusting what you paste.

The tunnel is public while it runs. It's a random hostname that disappears when
you stop the notebook, which is fine for development, but don't post the URL
anywhere. `WORKER_TOKEN` / `REMOTE_ASR_TOKEN` add a shared secret if you want it
locked down.

Failures are loud on purpose. If the worker is unreachable the request fails with
`Remote ASR call failed` rather than silently falling back to CPU, so a dead
tunnel can't be mistaken for a working one.

The first run downloads about 3 GB of `large-v3` weights inside Colab. That's
Google's bandwidth, not yours, and it takes a couple of minutes.

## Verification

Before relying on Colab, the remote path was tested locally by running a second
transcriber instance as a stand-in worker:

```
REMOTE RESULT
  meta     : {'remote': True, 'endpoint': 'http://127.0.0.1:8010'}
  language : en
  text     : " What's the most important key to success?  I think it's hunger. …"
```

So the plumbing was known good before any GPU was involved. The worker endpoint
itself (`POST /api/v1/transcribe/raw`), which is the exact contract Colab serves,
was also checked directly:

```
model: small | device: cpu | int8 | language: en (0.996) | realtime x: 0.52
```

## During a demo

If Colab isn't running, everything still works on CPU, just slower. Nothing
breaks and the extension behaves identically. Run `use_gpu.py --status` beforehand
so you know which mode you're in.

Worth doing either way: transcribe the reels you plan to show a few minutes
before. Results are cached, so they come back instantly during the demo and
survive the tunnel dying.
