"""End-to-end smoke test against a local media file.

    python scripts/smoke_test.py <path-to-audio-or-video> [--language ur]

Downloads the Whisper weights on first run.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.orchestrator import TranscriptionRequest, run_pipeline  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("media", help="local file path or a URL")
    ap.add_argument("--language", default=None, help="force a language code, e.g. ur")
    ap.add_argument("--task", default="transcribe", choices=["transcribe", "translate"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--json", action="store_true", help="dump the full JSON result")
    args = ap.parse_args()

    p = Path(args.media)
    if p.exists():
        req = TranscriptionRequest(
            upload_path=p, upload_name=p.name,
            language=args.language, task=args.task, model=args.model,
        )
    else:
        req = TranscriptionRequest(
            url=args.media, language=args.language, task=args.task, model=args.model,
        )

    t0 = time.perf_counter()

    def progress(pct: float, msg: str) -> None:
        bar = "#" * int(pct * 30)
        print(f"\r  [{bar:<30}] {pct * 100:5.1f}%  {msg[:45]:<45}", end="", flush=True)

    try:
        out = run_pipeline(req, progress=progress)
    except Exception as exc:
        print(f"\n\nFAILED: {type(exc).__name__}: {exc}")
        return 1

    print("\n")
    d = out.as_dict()

    if args.json:
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return 0

    lang, tr, ci, eng = d["language"], d["transcript"], d["classifier_input"], d["engine"]

    print("=" * 72)
    print(f"  LANGUAGE   : {lang.get('language_name')} ({lang.get('language')})  "
          f"p={lang.get('probability')}")
    if lang.get("corrected"):
        print(f"  CORRECTED  : {lang.get('reason')}")
    if lang.get("script_repair", {}).get("applied"):
        print(f"  SCRIPT FIX : {lang['script_repair']['method']}")
    print(f"  QUALITY    : {tr['quality']}  (confidence {tr['confidence']})")
    print(f"  SEGMENTS   : {tr['kept_segments']} kept / {tr['dropped_segments']} dropped")
    print(f"  ENGINE     : {eng['model']} on {eng['device']}/{eng['compute_type']}  "
          f"RTF={eng['realtime_factor']}x")
    print(f"  MEDIA      : {d['media']['duration_seconds']}s")
    print(f"  TIMINGS    : {d['timings']}")
    print("=" * 72)
    print("\nTRANSCRIPT:\n")
    print(tr["text"] or "  (empty)")

    if tr["stats"].get("drop_reasons"):
        print("\nFILTERED OUT:")
        for reason, n in tr["stats"]["drop_reasons"].items():
            print(f"  {n:3d} x  {reason}")

    if d["warnings"]:
        print("\nWARNINGS:")
        for w in d["warnings"]:
            print(f"  - {w}")

    print(f"\nCLASSIFIER INPUT: {ci['char_count']} chars, sources={ci['sources']}, "
          f"reliable={ci['is_reliable']}")
    print(f"\nWall clock: {time.perf_counter() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
