"""Generate TrustLens_GPU_Worker.ipynb.

Kept as a generator rather than a hand-maintained .ipynb because notebook JSON is
painful to edit by hand and easy to corrupt.

    python colab/build_notebook.py
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "TrustLens_GPU_Worker.ipynb"


def md(*lines: str) -> dict:
    return {"cell_type": "markdown", "metadata": {},
            "source": [l + "\n" for l in lines]}


def code(*lines: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None,
            "outputs": [], "source": [l + "\n" for l in lines]}


cells = [
    md(
        "# TrustLens — Whisper GPU Worker",
        "",
        "Runs **Module 12's ASR stage on a free Colab T4**, so your laptop can use",
        "`large-v3` at usable speed instead of `small` at 1.6× realtime.",
        "",
        "Your laptop keeps doing everything else — downloading the reel, extracting",
        "audio, filtering hallucinations, chunking for the classifier. Only the",
        "expensive Whisper decode moves here.",
        "",
        "**Before you start:** `Runtime → Change runtime type → T4 GPU`.",
        "",
        "---",
        "### Two things to know",
        "",
        "1. **Free Colab disconnects** after ~90 min idle or ~12 h total. The tunnel URL",
        "   dies with it. Re-run this notebook and paste the new URL — it changes every time.",
        "2. **The tunnel is public.** Anyone with the URL can send audio to it while it",
        "   runs. It is a random unguessable hostname and it disappears when you stop the",
        "   notebook, which is fine for development — but do not post the URL anywhere,",
        "   and set `WORKER_TOKEN` below if you want a shared secret.",
    ),

    md("## 1 · Confirm you actually got a GPU"),
    code(
        "!nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv",
        "",
        "import subprocess, sys",
        "out = subprocess.run(['nvidia-smi'], capture_output=True, text=True)",
        "if out.returncode != 0:",
        "    print('\\nNO GPU. Runtime -> Change runtime type -> T4 GPU, then rerun.')",
        "    sys.exit(1)",
        "print('\\nGPU ready.')",
    ),

    md("## 2 · Install dependencies", "",
       "~1 minute. `faster-whisper` brings CTranslate2 with CUDA support."),
    code(
        "%pip install -q faster-whisper==1.2.1 fastapi uvicorn python-multipart \\",
        "    pydantic-settings sqlalchemy aiofiles httpx yt-dlp imageio-ffmpeg nest_asyncio",
        "print('done')",
    ),

    md(
        "## 3 · Upload your code bundle",
        "",
        "On your laptop run:",
        "",
        "```bash",
        "python scripts/make_colab_bundle.py",
        "```",
        "",
        "then upload the `colab_bundle.zip` it produces when prompted below.",
        "",
        "This runs the *same* pipeline code as your laptop — same Urdu language policy,",
        "same hallucination filter. A hand-written mini-server here would silently give",
        "different results from your local runs.",
    ),
    code(
        "import zipfile, os, sys",
        "from pathlib import Path",
        "from google.colab import files",
        "",
        "WORK = Path('/content/trustlens')",
        "WORK.mkdir(parents=True, exist_ok=True)",
        "os.chdir(WORK)",
        "",
        "if not (WORK / 'app').exists():",
        "    print('Upload colab_bundle.zip ...')",
        "    up = files.upload()",
        "    name = next(iter(up))",
        "    with zipfile.ZipFile(name) as z:",
        "        z.extractall(WORK)",
        "    print('extracted to', WORK)",
        "else:",
        "    print('app/ already present, skipping upload')",
        "",
        "sys.path.insert(0, str(WORK))",
        "assert (WORK / 'app' / 'pipeline' / 'asr.py').exists(), 'app/ missing - re-upload'",
        "print('code ready')",
    ),

    md(
        "## 4 · Configure for GPU",
        "",
        "`large-v3` in `float16` needs ~5 GB of the T4's 15 GB. If you ever hit an OOM,",
        "switch `ASR_COMPUTE_TYPE` to `int8_float16`.",
    ),
    code(
        "import os",
        "",
        "os.environ['ASR_MODEL']        = 'large-v3'   # the scope document's model",
        "os.environ['ASR_DEVICE']       = 'cuda'",
        "os.environ['ASR_COMPUTE_TYPE'] = 'float16'   # int8_float16 if you hit OOM",
        "os.environ['ASR_BACKEND']      = 'local'     # this box IS the worker",
        "os.environ['JOB_WORKERS']      = '1'",
        "os.environ['DATA_DIR']         = '/content/trustlens/data'",
        "",
        "# Optional shared secret. Set the same value as REMOTE_ASR_TOKEN on your laptop.",
        "WORKER_TOKEN = ''",
        "",
        "from app.config import get_settings",
        "get_settings.cache_clear()",
        "from app.config import settings",
        "print('model      :', settings.asr_model)",
        "print('device     :', settings.resolve_device())",
    ),

    md("## 5 · Preload the model", "",
       "First run downloads ~3 GB. Doing it now means the first real request is fast."),
    code(
        "import time",
        "from app.pipeline.asr import warm_up",
        "",
        "t0 = time.time()",
        "print(warm_up())",
        "print(f'ready in {time.time()-t0:.0f}s')",
    ),

    md("## 6 · Quick benchmark", "",
       "Proves the GPU is actually being used. Watch the realtime factor —",
       "a T4 should be well above 10×, versus ~1.6× on a CPU laptop."),
    code(
        "import numpy as np, soundfile as sf, time",
        "from pathlib import Path",
        "",
        "# 30 s of quiet noise - we are timing throughput, not measuring accuracy",
        "p = Path('/content/bench.wav')",
        "sf.write(p, (np.random.randn(16000*30)*0.01).astype('float32'), 16000)",
        "",
        "from app.pipeline.asr import transcribe",
        "t0 = time.time()",
        "r = transcribe(p, language='en')",
        "dt = time.time() - t0",
        "print(f'30s audio decoded in {dt:.1f}s  ->  {30/dt:.1f}x realtime')",
        "print('device:', r.device, r.compute_type)",
    ),

    md(
        "## 7 · Start the server and open a public tunnel",
        "",
        "`cloudflared` gives a free HTTPS URL with no signup. The server runs in a",
        "background thread so this cell returns and the notebook stays usable.",
    ),
    code(
        "!wget -q -O /usr/local/bin/cloudflared \\",
        "  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
        "!chmod +x /usr/local/bin/cloudflared",
        "print('cloudflared installed')",
    ),
    code(
        "import threading, time, uvicorn, nest_asyncio",
        "nest_asyncio.apply()",
        "",
        "from app.main import app as fastapi_app",
        "",
        "def _serve():",
        "    uvicorn.run(fastapi_app, host='0.0.0.0', port=8000, log_level='warning')",
        "",
        "threading.Thread(target=_serve, daemon=True).start()",
        "time.sleep(8)",
        "",
        "import httpx",
        "h = httpx.get('http://127.0.0.1:8000/api/v1/health', timeout=30).json()",
        "print('server up  |  model:', h['asr']['model'], '| device:', h['asr']['device'])",
    ),
    code(
        "import re, subprocess, time",
        "",
        "proc = subprocess.Popen(",
        "    ['cloudflared', 'tunnel', '--url', 'http://localhost:8000', '--no-autoupdate'],",
        "    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)",
        "",
        "public_url = None",
        "deadline = time.time() + 90",
        "while time.time() < deadline:",
        "    line = proc.stdout.readline()",
        "    if not line:",
        "        continue",
        "    m = re.search(r'https://[-a-z0-9]+\\.trycloudflare\\.com', line)",
        "    if m:",
        "        public_url = m.group(0)",
        "        break",
        "",
        "if not public_url:",
        "    print('Tunnel did not come up. Re-run this cell.')",
        "else:",
        "    print('=' * 66)",
        "    print('  Add these two lines to your laptop .env:')",
        "    print()",
        "    print('    ASR_BACKEND=remote')",
        "    print(f'    REMOTE_ASR_URL={public_url}')",
        "    print()",
        "    print('  Then restart your local server:  python run.py')",
        "    print('=' * 66)",
    ),

    md(
        "## 8 · Verify from the public URL",
        "",
        "Confirms the tunnel actually reaches the worker before you rely on it.",
    ),
    code(
        "import httpx",
        "r = httpx.get(public_url + '/api/v1/health', timeout=60).json()",
        "print('reachable :', r['status'])",
        "print('model     :', r['asr']['model'])",
        "print('device    :', r['asr']['device'], '/', r['asr']['compute_type'])",
        "assert r['asr']['device'] == 'cuda', 'not running on GPU!'",
        "print('\\nGPU worker live. Point your laptop at it.')",
    ),

    md(
        "---",
        "## Keeping it alive",
        "",
        "Leave this tab open. Free Colab stops on ~90 min of inactivity, and the browser",
        "tab counts as activity. When it dies:",
        "",
        "1. Re-run the notebook (the model download is cached only within a session, so",
        "   expect the ~3 GB fetch again).",
        "2. Copy the **new** URL — it is different every session.",
        "3. Update `REMOTE_ASR_URL` on your laptop and restart `python run.py`.",
        "",
        "If the laptop cannot reach the worker, it fails with a clear",
        "`Remote ASR call failed` error rather than silently falling back — so you will",
        "never mistake a dead tunnel for a working one. To go back to local CPU, set",
        "`ASR_BACKEND=local`.",
    ),
]

nb = {
    "nbformat": 4,
    "nbformat_minor": 0,
    "metadata": {
        "colab": {"provenance": [], "gpuType": "T4", "toc_visible": True},
        "kernelspec": {"name": "python3", "display_name": "Python 3"},
        "language_info": {"name": "python"},
        "accelerator": "GPU",
    },
    "cells": cells,
}

OUT.write_text(json.dumps(nb, indent=1), encoding="utf-8")
print(f"Wrote {OUT}  ({OUT.stat().st_size/1024:.0f} KB, {len(cells)} cells)")
