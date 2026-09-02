"""Check that everything this module needs is actually working.

    python scripts/doctor.py

Prints a pass/fail line per dependency and tells you how to fix whatever failed.
"""
from __future__ import annotations

import io
import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OK, WARN, FAIL = "[ OK ]", "[WARN]", "[FAIL]"
problems: list[str] = []


def check(label: str, fn):
    try:
        status, detail = fn()
    except Exception as exc:
        status, detail = FAIL, f"{type(exc).__name__}: {str(exc)[:150]}"
    print(f"  {status}  {label:<26} {detail}")
    if status == FAIL:
        problems.append(label)


def c_python():
    v = sys.version_info
    s = f"{v.major}.{v.minor}.{v.micro}"
    return (OK, s) if v >= (3, 10) else (FAIL, f"{s} - need 3.10+")


def c_deps():
    import faster_whisper, fastapi, sqlalchemy, yt_dlp  # noqa: F401
    return OK, f"faster-whisper {faster_whisper.__version__}, yt-dlp {yt_dlp.version.__version__}"


def c_ffmpeg():
    from app.pipeline.ffmpeg_tools import ffmpeg_path
    p = ffmpeg_path()
    kind = "bundled" if "imageio_ffmpeg" in p else "system"
    return OK, f"{kind} ({Path(p).name})"


def c_device():
    from app.config import settings
    dev, comp = settings.resolve_device()
    threads = settings.resolve_cpu_threads()
    if dev == "cuda":
        return OK, f"GPU / {comp} - large-v3 is practical"
    return WARN, f"CPU / {comp}, {threads} threads - use ASR_MODEL=small or medium"


def c_model():
    from app.config import settings
    root = settings.models_dir
    hits = list(root.glob(f"**/*{settings.asr_model}*"))
    if hits:
        mb = sum(f.stat().st_size for f in root.rglob("*") if f.is_file()) / 1048576
        return OK, f"{settings.asr_model} cached ({mb:.0f} MB)"
    return WARN, f"{settings.asr_model} not downloaded yet - happens on first run"


def c_db():
    from app.config import settings
    from app.db import init_db
    init_db()
    return OK, settings.sqlalchemy_url.split("://", 1)[0]


def c_env():
    from app.config import BASE_DIR
    return (OK, ".env found") if (BASE_DIR / ".env").exists() else \
           (WARN, "no .env - defaults apply (fine)")


def c_ocr():
    from app.config import settings
    from app.pipeline import ocr
    if not settings.ocr_enabled:
        return OK, "disabled (optional)"
    return (OK, "enabled + installed") if ocr.is_available() else \
           (FAIL, "enabled but EasyOCR missing - pip install -r requirements-optional.txt")


def c_cookies():
    """Instagram URL fetching needs cookies. Counts only, never reads values."""
    from yt_dlp.cookies import extract_cookies_from_browser

    from app.config import settings

    # A working cookies.txt is the whole answer - do not nag about browsers then.
    cf = settings.resolved_cookiefile
    if cf:
        text = Path(cf).read_text(errors="ignore")
        lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
        has_ig = any("instagram" in ln.lower() for ln in lines)
        if has_ig:
            return OK, f"{len(lines)} cookies from {Path(cf).name} (Instagram covered)"
        return WARN, f"{Path(cf).name} found but has no Instagram cookies - re-export"

    results = []
    for browser in ("chrome", "edge", "firefox"):
        try:
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf), contextlib.redirect_stdout(buf):
                jar = extract_cookies_from_browser(browser)
            logged_in = any(
                c.name == "sessionid" and "instagram" in (c.domain or "") for c in jar
            )
            results.append(f"{browser}={'instagram OK' if logged_in else 'no IG login'}")
        except Exception as exc:
            msg = str(exc)
            if "copy" in msg.lower() or "locked" in msg.lower():
                results.append(f"{browser}=locked (quit the browser first)")
            elif "dpapi" in msg.lower() or "decrypt" in msg.lower():
                results.append(f"{browser}=encrypted (use a cookies.txt export)")
            else:
                results.append(f"{browser}=unavailable")

    good = any("OK" in r for r in results)
    return (OK if good else WARN), ", ".join(results)


print()
print("TrustLens Video-to-Text Transcriber - setup check")
print("=" * 74)
print(" Core (required to run)")
check("Python version", c_python)
check("Python packages", c_deps)
check("FFmpeg", c_ffmpeg)
check("Database", c_db)
check("Config file", c_env)
print()
print(" Model")
check("Compute device", c_device)
check("Whisper weights", c_model)
print()
print(" Optional features")
check("OCR fallback", c_ocr)
check("Instagram cookies", c_cookies)
print("=" * 74)

if problems:
    print(f"\n {len(problems)} blocking problem(s): {', '.join(problems)}")
    print(" Fix those, then re-run this script.\n")
    raise SystemExit(1)

print("\n Core checks passed - you can run:  python run.py")
print(" Then open http://127.0.0.1:8000\n")
print(" Uploading a file works with no further setup.")
print(" Instagram URLs additionally need cookies - see 'Instagram cookies' above.\n")
