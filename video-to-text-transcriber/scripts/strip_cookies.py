"""Reduce a cookies.txt to only the domains this project actually needs.

    python scripts/strip_cookies.py [path]

Browser "export all cookies" extensions do exactly what they say: they dump
every session in the browser. That file then contains live tokens for your
email, your bank, and everything else you happen to be logged into - sitting in
a project directory, one bad .gitignore away from a public repository.

yt-dlp only ever needs the cookies for the site it is downloading from, so we
throw the rest away. Run this immediately after any export.
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

KEEP_DOMAINS = ("instagram.com", "cdninstagram.com", "tiktok.com", "tiktokcdn.com")


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("cookies.txt")
    if not path.exists():
        print(f"Not found: {path}")
        return 1

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    header, kept, dropped_domains = [], [], set()

    for ln in lines:
        if not ln.strip():
            continue
        if ln.startswith("#"):
            if "Netscape" in ln or "HTTP Cookie File" in ln:
                header.append(ln)
            continue
        domain = ln.split("\t")[0].lstrip(".").lower()
        if any(d in domain for d in KEEP_DOMAINS):
            kept.append(ln)
        else:
            dropped_domains.add(domain)

    if not header:
        header = ["# Netscape HTTP Cookie File"]

    if not kept:
        print("WARNING: no Instagram or TikTok cookies found. Leaving the file alone.")
        print("Re-export while logged in to Instagram.")
        return 1

    backup = path.with_suffix(f".unsafe-backup-{datetime.now():%Y%m%d%H%M%S}.txt")
    shutil.copy2(path, backup)
    path.write_text("\n".join(header + kept) + "\n", encoding="utf-8")

    print(f"Kept    : {len(kept)} cookies for {', '.join(KEEP_DOMAINS[:2])} ...")
    print(f"Removed : {len(dropped_domains)} other domains")
    print()
    print("Domains removed (first 25):")
    for d in sorted(dropped_domains)[:25]:
        print(f"  - {d}")
    if len(dropped_domains) > 25:
        print(f"  ... and {len(dropped_domains) - 25} more")
    print()
    print(f"The original was copied to:\n  {backup.name}")
    print("It still holds every token from the export. DELETE IT once you have")
    print("confirmed downloads still work:")
    print(f"  del \"{backup}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
