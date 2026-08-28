# Demo runbook

Setup notes for running the whole stack in front of an audience. About five
minutes, most of which is Colab installing itself while you do the other steps.

Order matters in one place only: point the laptop at the GPU *before* the
transcriber starts, otherwise it won't pick up the setting. That's why Colab comes
first.

## 1. Start the Colab GPU

Do this first so it installs in the background while you carry on.

1. Open <https://colab.research.google.com> and sign in.
2. File → Upload notebook, choose
   `D:\video-to-text transcriber\colab\TrustLens_GPU_Worker.ipynb`
3. Runtime → Change runtime type → T4 GPU → Save. Do this before running anything.
4. Runtime → Run all. When a cell asks for a file, upload
   `D:\video-to-text transcriber\colab_bundle.zip`
5. The last cell prints a URL like `https://something-random.trycloudflare.com`.
   Copy it and leave the Colab tab open for the whole demo.

Model loading takes two or three minutes. Start on step 2 while it works.

## 2. Point the laptop at the GPU

```bash
cd "D:\video-to-text transcriber" && .\.venv\Scripts\python.exe scripts\use_gpu.py PASTE_URL_HERE
```

You want to see:

```
model   large-v3
device  cuda
```

If it says `device cpu`, the T4 setting in step 1.3 didn't take. Fix that and run
this again.

## 3. Start the four services

```bash
powershell -ExecutionPolicy Bypass -File D:\trustlens-extension\start_all.ps1
```

Four windows open. Give them about 30 seconds; the misinformation model is 1 GB
and loads last. After a cold boot it can take closer to 80 seconds.

Check <http://127.0.0.1:8100/health>. All three modules should read `"up":true`.
The extension popup shows the same thing as a dot per service.

## 4. Load the extension

Only needed once per machine. Skip it if the shield is already in the toolbar.

1. Chrome → `chrome://extensions`
2. Turn on Developer mode, top right
3. Load unpacked → `D:\trustlens-extension\extension` (the inner folder, not the
   repo root)

If extension code changed since last time, click the reload arrow on the TrustLens
card. Editing files isn't enough on its own, Chrome keeps running its cached copy
until you reload the extension. Refreshing the Instagram tab does not do this.

## 5. Run through it

1. Open <https://www.instagram.com> and log in.
2. Scroll the feed. The badge sits top right and follows whichever post is in
   view.
3. Press "Why?" on a badge for the plain-English explanation.
4. Open a reel, press "Listen to audio", watch the progress bar, then the
   transcript appears in a "What the video said" box and the verdict updates.

## Pre-transcribe the reels you plan to show

Free Colab idles out after about 90 minutes and the tunnel goes with it. If that
happens mid-demo, "Listen to audio" fails.

A few minutes beforehand, open each reel you intend to show and press "Listen to
audio" once. Results are cached, so during the demo they come back instantly, and
they keep working even if the tunnel has since dropped. It also stops everyone
watching a progress bar for a minute.

## When something looks wrong

| Symptom | Cause | Fix |
|---|---|---|
| Popup says gateway down | services not started, or still booting | run step 3, wait 30s, press "Re-check services" |
| Gateway up, one module dot red | that service's window died, or it's still warming up | check the window for an error; give the classifier a minute after boot |
| "Listen to audio" errors with `getaddrinfo failed` | Colab tunnel died | re-run the notebook, redo step 2 with the new URL, restart the transcriber; or fall back to a pre-transcribed reel |
| `use_gpu.py` reports `device cpu` | T4 not selected in Colab | Runtime → Change runtime type → T4 GPU, re-run the notebook |
| No badges on Instagram | extension disabled, or old code cached | check "Enabled" in the popup; reload the extension per step 4 |
| Badge shows but sits at the bottom, full width | old extension code still loaded | reload the extension, then refresh the tab |

## Fallback with no Colab

Everything except reel audio is local and has no external dependency: captions,
on-screen text, account checks and the explanations all work offline. Switch the
transcriber back to CPU:

```bash
cd "D:\video-to-text transcriber" && .\.venv\Scripts\python.exe scripts\use_gpu.py --local
```

Restart the transcriber window afterwards. Reel transcription still runs, just at
roughly 6x the reel's length, which is exactly what the pre-transcribing step
above is for.
