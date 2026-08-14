"""
TrustLens - Fake Follower Detection  |  Command-line demo

Classify a REAL Instagram account as Real or Fake, live.

    python check_user.py ali.ahmad.r8            # scrape via Apify + classify
    python check_user.py ali.ahmad.r8 --no-cache # force a fresh Apify scrape
    python check_user.py --manual                # type the 7 numbers by hand
                                                 # (offline fallback, no token)

Requires a trained model first:  python train_and_save.py
For live scraping set:  $env:APIFY_API_TOKEN = "apify_api_xxx"
"""
import argparse
import sys

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from predict_core import (
    load_artifacts, predict_account, verdict_label, RAW_FEATURES, RAW_LABELS,
)

console = Console()


def manual_raw() -> dict:
    """Ask the user for the 7 raw features - offline fallback."""
    console.print("[bold]Manual entry[/bold] (offline mode). Enter each value:")
    def ask(prompt, cast, default=None):
        while True:
            raw = console.input(f"  {prompt}: ").strip()
            if raw == "" and default is not None:
                return default
            try:
                return cast(raw)
            except ValueError:
                console.print("    [red]invalid, try again[/red]")
    return {
        "profile_pic": ask("Has profile picture? 1=yes 0=no", int),
        "username_digit_ratio": ask("Digits-in-username ratio (0..1, e.g. 0.2)", float),
        "description_length": ask("Bio length in characters", int),
        "private": ask("Private account? 1=yes 0=no", int),
        "posts_count": ask("Number of posts", int),
        "followers_count": ask("Number of followers", int),
        "follows_count": ask("Number of following", int),
    }


def show_profile(summary: dict) -> None:
    v = " [cyan]verified[/cyan]" if summary.get("verified") else ""
    b = " [magenta]business[/magenta]" if summary.get("is_business") else ""
    bio = (summary.get("biography") or "").replace("\n", " ")
    if len(bio) > 70:
        bio = bio[:70] + "..."
    console.print(Panel(
        f"[bold]@{summary.get('username','?')}[/bold]{v}{b}\n"
        f"{summary.get('full_name','')}\n[dim]{bio}[/dim]",
        title="Instagram profile", border_style="blue", box=box.ROUNDED,
    ))


def show_features(raw: dict) -> None:
    t = Table(title="Extracted features", box=box.SIMPLE_HEAVY, header_style="bold")
    t.add_column("Attribute")
    t.add_column("Value", justify="right")
    for k in RAW_FEATURES:
        val = raw[k]
        if k == "username_digit_ratio":
            val = f"{val:.3f}"
        elif k in ("profile_pic", "private"):
            val = "Yes" if val else "No"
        else:
            val = f"{val:,}"
        t.add_row(RAW_LABELS[k], str(val))
    console.print(t)


def show_verdict(prob_fake: float) -> None:
    v = verdict_label(prob_fake)
    color = {"real": "green", "fake": "red", "uncertain": "yellow"}[v["band"]]
    note = ("\n[dim]Confidence < 60% -> flagged for manual review "
            "(per TrustLens policy).[/dim]" if v["band"] == "uncertain" else "")
    bar_len = 30
    filled = max(0, min(bar_len, int(round(prob_fake * bar_len))))
    bar = "#" * filled + "-" * (bar_len - filled)
    console.print(Panel(
        f"[bold {color}]{v['text']}[/bold {color}]\n\n"
        f"Model confidence: [bold]{v['confidence']:.1%}[/bold]\n"
        f"Fake probability: {prob_fake:.1%}\n"
        f"[dim]0% real [{bar}] 100% fake[/dim]{note}",
        title="TrustLens verdict", border_style=color, box=box.DOUBLE,
    ))


def main() -> None:
    ap = argparse.ArgumentParser(description="TrustLens fake-follower check")
    ap.add_argument("username", nargs="?", help="Instagram username (without @)")
    ap.add_argument("--manual", action="store_true", help="type the 7 numbers by hand (offline)")
    ap.add_argument("--no-cache", action="store_true", help="force a fresh Apify scrape")
    args = ap.parse_args()

    try:
        model, scaler, thresholds = load_artifacts()
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    summary = None
    if args.manual or not args.username:
        raw = manual_raw()
    else:
        from apify_scraper import scrape_profile, profile_to_raw_features, profile_summary
        with console.status(f"[cyan]Scraping @{args.username} via Apify...[/cyan]"):
            try:
                profile = scrape_profile(args.username, use_cache=not args.no_cache)
            except Exception as e:
                console.print(f"[red]Scrape failed:[/red] {e}")
                console.print("[yellow]Tip:[/yellow] run with --manual to enter values by hand.")
                sys.exit(1)
        raw = profile_to_raw_features(profile)
        summary = profile_summary(profile)

    _, prob_fake, _ = predict_account(raw, model, scaler, thresholds)

    console.print()
    if summary:
        show_profile(summary)
    show_features(raw)
    show_verdict(prob_fake)


if __name__ == "__main__":
    main()
