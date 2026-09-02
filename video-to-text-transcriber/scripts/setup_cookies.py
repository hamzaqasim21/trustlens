"""Get URL-based downloading working for Instagram.

    python scripts/setup_cookies.py            # diagnose and advise
    python scripts/setup_cookies.py --test URL # try an actual download

Instagram refuses anonymous downloads. yt-dlp needs the cookies from a browser
where you are logged in. There are two ways to supply them, and this script
works out which one will actually work on this machine.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import BASE_DIR, settings  # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def browser_is_running(name: str) -> bool:
    exe = {"chrome": "chrome.exe", "edge": "msedge.exe",
           "firefox": "firefox.exe", "brave": "brave.exe"}.get(name)
    if not exe:
        return False
    try:
        import subprocess
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe}"],
            capture_output=True, text=True, timeout=20,
        ).stdout.lower()
        return exe.lower() in out
    except Exception:
        return False


def probe(browser: str) -> tuple[str, str]:
    """Returns (state, detail). state in ok | locked | encrypted | missing | error."""
    from yt_dlp.cookies import extract_cookies_from_browser

    try:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf), contextlib.redirect_stdout(buf):
            jar = extract_cookies_from_browser(browser)
    except Exception as exc:
        msg = ANSI.sub("", str(exc)).lower()
        if "could not copy" in msg or "locked" in msg or "permission" in msg:
            return "locked", "cookie database is locked by the running browser"
        if "dpapi" in msg or "decrypt" in msg:
            return "encrypted", "App-Bound Encryption blocks reading these cookies"
        if "not find" in msg or "no such" in msg or "unsupported" in msg:
            return "missing", "browser not installed"
        return "error", ANSI.sub("", str(exc))[:120]

    ig = any(c.name == "sessionid" and "instagram" in (c.domain or "") for c in jar)
    marks = []
    if ig:
        marks.append("Instagram logged in")
    return "ok", (", ".join(marks) if marks else "readable, but no IG/YT login found")


def cookiefile_state() -> tuple[bool, str]:
    """Validate whatever cookies.txt we can find, and report what it covers."""
    p = settings.resolved_cookiefile
    if not p:
        return False, (
            f"none found (drop one at {BASE_DIR / 'cookies.txt'} "
            f"and it is picked up automatically)"
        )

    f = Path(p)
    text = f.read_text(errors="ignore")
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]

    if not lines:
        return False, f"{f.name} exists but contains no cookies"
    if "# Netscape HTTP Cookie File" not in text and "# HTTP Cookie File" not in text:
        return False, (
            f"{f.name} is not in Netscape format - re-export and make sure you "
            f"pick the 'Netscape'/'cookies.txt' option, not JSON"
        )

    domains = {ln.split("\t")[0].lstrip(".").lower() for ln in lines if "\t" in ln}
    sites = []
    for want, label in (("instagram.com", "Instagram"),
                        ("tiktok.com", "TikTok")):
        if any(want in d for d in domains):
            sites.append(label)

    has_ig_session = any(
        "instagram" in ln.lower() and "sessionid" in ln.lower() for ln in lines
    )

    detail = f"{len(lines)} cookies from {f.name}"
    if sites:
        detail += f" - covers {', '.join(sites)}"
    else:
        detail += " - but no Instagram/TikTok cookies in it"
    if any("Instagram" in s for s in sites) and not has_ig_session:
        detail += " (WARNING: no sessionid - you may not have been logged in)"

    return bool(sites), detail


def test_download(url: str) -> None:
    from app.pipeline.acquire import AcquisitionError, fetch_from_url, new_workdir
    import shutil

    print(f"\nAttempting a real download:\n  {url}\n")
    wd = new_workdir()
    try:
        asset = fetch_from_url(url, wd)
        mb = asset.path.stat().st_size / 1048576
        print(f"  SUCCESS - {asset.path.name} ({mb:.1f} MB)")
        print(f"  platform={asset.platform}  title={asset.title[:60]}")
        print("\n  URL downloads work. You are done.\n")
    except AcquisitionError as exc:
        print(f"  FAILED\n\n  {exc}\n")
    finally:
        shutil.rmtree(wd, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", metavar="URL", help="try downloading this URL")
    args = ap.parse_args()

    print()
    print("Cookie setup for URL downloads")
    print("=" * 74)

    ok, detail = cookiefile_state()
    print(f"\n  cookies.txt file : {'OK' if ok else '--'}  {detail}")

    print("\n  browsers:")
    usable = []
    for b in ("chrome", "edge", "firefox", "brave"):
        state, why = probe(b)
        running = " (running)" if browser_is_running(b) else ""
        if state == "missing":
            continue
        flag = "OK  " if state == "ok" else "--  "
        print(f"    {flag}{b}{running}: {why}")
        if state == "ok":
            usable.append(b)

    print("\n" + "=" * 74)

    if ok:
        print("\n  You already have a working cookies.txt. Test it:")
        print("    python scripts/setup_cookies.py --test <instagram-url>\n")
    elif usable:
        b = usable[0]
        print(f"\n  RECOMMENDED - {b} cookies are readable. Put this in your .env:\n")
        print(f"    YTDLP_COOKIES_FROM_BROWSER={b}\n")
    else:
        print("""
  No browser cookies are readable, so use the cookies.txt route. It is more
  reliable anyway, and unlike the browser route it does NOT require quitting
  your browser.

    1. Install the "Get cookies.txt LOCALLY" extension in Chrome.
    2. Go to instagram.com while logged in. Click the extension and export
       cookies FOR THIS SITE ONLY, in Netscape format.

       Do not use "export all cookies". That dumps every session in the
       browser - email, banking, everything - into one plaintext file sitting
       in a project directory. Site-only is all yt-dlp needs.

    3. Save it as cookies.txt in the project root:
""" + f"         {BASE_DIR / 'cookies.txt'}" + """

       It is picked up automatically - no .env edit needed.

    4. Re-run this script to confirm, then test:
         python scripts/setup_cookies.py --test <instagram-url>

  If you already ran an "export all" by mistake, clean it up:
         python scripts/strip_cookies.py

  ALTERNATIVE: skip all of this and upload the video file. That path needs no
  cookies at all and is the safer choice for a live demo.
""")

    if args.test:
        test_download(args.test)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
