"""
Switch the ASR backend between this laptop's CPU and a free Colab GPU worker.

    python scripts/use_gpu.py https://something.trycloudflare.com   # use the GPU
    python scripts/use_gpu.py --local                               # back to CPU
    python scripts/use_gpu.py --status                              # what's set now

Why this exists rather than "just edit .env": the Colab tunnel URL changes every
session, so this edit happens often, and a typo or a dead tunnel produces a
failure much later — during a transcription — where it looks like a bug in the
pipeline. This checks the worker is actually alive and actually a TrustLens
worker *before* writing anything, so a bad URL is caught in two seconds.

Nothing here touches the running server: restart it afterwards to pick up the
change.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import httpx
except ImportError:                                    # pragma: no cover
    sys.exit("httpx is missing. Run:  pip install -r requirements.txt")

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"

GREEN, RED, YELLOW, DIM, RESET = (
    "\033[92m", "\033[91m", "\033[93m", "\033[2m", "\033[0m"
)


def read_env() -> list[str]:
    if not ENV.exists():
        example = ROOT / ".env.example"
        if example.exists():
            ENV.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"{DIM}Created .env from .env.example{RESET}")
        else:
            ENV.write_text("", encoding="utf-8")
    return ENV.read_text(encoding="utf-8").splitlines()


def set_key(lines: list[str], key: str, value: str) -> list[str]:
    """Set KEY=value, replacing any existing (or commented-out) definition."""
    pattern = re.compile(rf"^\s*#?\s*{re.escape(key)}\s*=", re.IGNORECASE)
    out, replaced = [], False
    for line in lines:
        if pattern.match(line):
            if not replaced:
                out.append(f"{key}={value}")
                replaced = True
            # Drop any later duplicates so the file has one source of truth.
        else:
            out.append(line)
    if not replaced:
        out.append(f"{key}={value}")
    return out


def get_key(lines: list[str], key: str) -> str | None:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=(.*)$", re.IGNORECASE)
    for line in lines:
        m = pattern.match(line)
        if m:
            return m.group(1).strip()
    return None


def write_env(lines: list[str]) -> None:
    text = "\n".join(lines).rstrip() + "\n"
    ENV.write_text(text, encoding="utf-8")


def check_worker(url: str) -> dict:
    """Confirm the URL is reachable AND is really a TrustLens worker.

    A Cloudflare tunnel that has died usually still resolves and answers with an
    HTML error page, so "it responded" is not enough — the shape of the response
    has to be checked too.
    """
    url = url.rstrip("/")
    health = f"{url}/api/v1/health"
    print(f"{DIM}Checking {health} …{RESET}")

    try:
        r = httpx.get(health, timeout=30.0, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise SystemExit(
            f"{RED}Could not reach that URL.{RESET}\n  {type(exc).__name__}: {exc}\n"
            f"  Is the Colab notebook still running? Free Colab stops after\n"
            f"  ~90 minutes idle, and the tunnel dies with it."
        )

    if r.status_code != 200:
        raise SystemExit(f"{RED}Worker answered HTTP {r.status_code}.{RESET} "
                         f"The tunnel is probably dead — re-run the notebook.")
    try:
        data = r.json()
    except Exception:
        raise SystemExit(
            f"{RED}That URL answered, but not with JSON.{RESET}\n"
            f"  It is probably a Cloudflare error page, not your worker."
        )
    if "asr" not in data:
        raise SystemExit(f"{RED}That is not a TrustLens worker.{RESET} "
                         f"Got keys: {list(data)[:6]}")
    return data


def main() -> None:
    args = [a for a in sys.argv[1:] if a.strip()]
    lines = read_env()

    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return

    # ---- status ----
    if args[0] in ("--status", "-s"):
        backend = get_key(lines, "ASR_BACKEND") or "local"
        url = get_key(lines, "REMOTE_ASR_URL") or ""
        model = get_key(lines, "ASR_MODEL") or "small"
        print(f"\n  ASR_BACKEND    {backend}")
        print(f"  ASR_MODEL      {model}")
        print(f"  REMOTE_ASR_URL {url or '(unset)'}\n")
        if backend == "remote" and url:
            try:
                info = check_worker(url)
                asr = info.get("asr", {})
                print(f"{GREEN}  Worker is alive{RESET} — {asr.get('model')} on "
                      f"{asr.get('device')}\n")
            except SystemExit as e:
                print(e)
        return

    # ---- back to local CPU ----
    if args[0] in ("--local", "-l", "local"):
        lines = set_key(lines, "ASR_BACKEND", "local")
        write_env(lines)
        print(f"\n{GREEN}Switched back to this laptop's CPU.{RESET}")
        print(f"{YELLOW}Restart the transcriber for it to take effect:{RESET}")
        print("  python run.py\n")
        return

    # ---- point at a GPU worker ----
    url = args[0].strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise SystemExit(f"{RED}That does not look like a URL:{RESET} {url!r}\n"
                         f"  Paste the https://…trycloudflare.com line the "
                         f"notebook printed.")

    info = check_worker(url)
    asr = info.get("asr", {})
    device = str(asr.get("device", "?"))
    model = asr.get("model", "?")

    lines = set_key(lines, "ASR_BACKEND", "remote")
    lines = set_key(lines, "REMOTE_ASR_URL", url)
    write_env(lines)

    print(f"\n{GREEN}Now using the remote worker.{RESET}")
    print(f"  model   {model}")
    print(f"  device  {device}")
    if "cuda" not in device.lower():
        print(f"\n{YELLOW}  Note: that worker reports '{device}', not CUDA.{RESET}")
        print(f"{YELLOW}  It will work, but you won't get the GPU speed-up.{RESET}")
        print(f"{YELLOW}  In Colab: Runtime -> Change runtime type -> T4 GPU.{RESET}")

    print(f"\n{YELLOW}Restart the transcriber for it to take effect:{RESET}")
    print("  python run.py\n")
    print(f"{DIM}The tunnel URL changes every Colab session — re-run this "
          f"script with the new one.{RESET}\n")


if __name__ == "__main__":
    main()
