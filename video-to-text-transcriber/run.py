"""Start the transcriber service.

    python run.py                 # normal
    python run.py --reload        # auto-restart on code changes
    python run.py --warmup        # preload the model before serving
"""
from __future__ import annotations

import argparse

import uvicorn

from app.config import settings


def main() -> None:
    ap = argparse.ArgumentParser(description="TrustLens Video-to-Text Transcriber")
    ap.add_argument("--host", default=settings.host)
    ap.add_argument("--port", type=int, default=settings.port)
    ap.add_argument("--reload", action="store_true", help="auto-reload on file changes")
    ap.add_argument("--warmup", action="store_true", help="load the Whisper model first")
    ap.add_argument("--log-level", default="info")
    args = ap.parse_args()

    if args.warmup:
        from app.pipeline.asr import warm_up

        print("Loading model (first run downloads weights)...")
        print(warm_up())

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
