"""Zip the pipeline code for upload to Colab.

    python scripts/make_colab_bundle.py

Produces `colab_bundle.zip` containing just the `app/` package - a few hundred
KB. Upload that to the Colab notebook so the GPU worker runs the *same* code as
your laptop, including the Urdu language policy and the hallucination filter.
Running a hand-written mini-server on Colab instead would quietly give you
different results from your local runs, which is the kind of discrepancy that
wastes a week.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "colab_bundle.zip"

SKIP_DIRS = {"__pycache__", ".pytest_cache", ".venv", "data"}


def main() -> int:
    app_dir = BASE / "app"
    if not app_dir.is_dir():
        print(f"ERROR: {app_dir} not found - run this from the project root.")
        return 1

    files: list[Path] = []
    for p in app_dir.rglob("*.py"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        files.append(p)

    if not files:
        print("ERROR: no Python files found under app/")
        return 1

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.relative_to(BASE))

    size_kb = OUT.stat().st_size / 1024
    print(f"Wrote {OUT.name}  ({size_kb:.0f} KB, {len(files)} files)")
    print()
    print("Next:")
    print("  1. Open colab/TrustLens_GPU_Worker.ipynb in Google Colab")
    print("  2. Runtime -> Change runtime type -> T4 GPU")
    print("  3. Run the cells; upload this zip when asked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
