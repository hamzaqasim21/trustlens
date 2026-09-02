"""Stage 1 - get a media file onto local disk.

Three entry points, matching the three ways TrustLens receives a video:
  * URL         -> yt-dlp (Instagram, and TikTok as a secondary target)
  * upload      -> the caller handed us the bytes
  * direct CDN  -> the browser extension already resolved the real video URL
                   from a logged-in Instagram page, so we just fetch it.

The extension path matters: Instagram increasingly walls reels behind a login,
and yt-dlp from a bare server gets blocked. The extension runs inside the
already-authenticated session of the person browsing, so the CDN URL it reads
off the page just works.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.pipeline.ffmpeg_tools import ffmpeg_path

log = logging.getLogger(__name__)

_SUPPORTED_HOSTS = (
    "instagram.com", "instagr.am", "cdninstagram.com", "fbcdn.net",
    "tiktok.com", "tiktokcdn.com",
)


class AcquisitionError(RuntimeError):
    """Raised when we cannot obtain the media."""


@dataclass
class MediaAsset:
    path: Path
    source_kind: str                 # url | upload | direct
    source_ref: str                  # original url or filename
    platform: str = "unknown"
    duration: float = 0.0
    has_audio: bool = False
    has_video: bool = False
    width: int = 0
    height: int = 0
    title: str = ""
    uploader: str = ""
    meta: dict = field(default_factory=dict)


def detect_platform(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if "instagram" in host or "cdninstagram" in host or "fbcdn" in host:
        return "instagram"
    if "tiktok" in host:
        return "tiktok"
    return "unknown"


def is_supported_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(h in host for h in _SUPPORTED_HOSTS)


def new_workdir() -> Path:
    d = settings.media_dir / uuid.uuid4().hex[:16]
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------- #
# URL -> yt-dlp
# --------------------------------------------------------------------------- #
def _ytdlp_options(workdir: Path, platform: str = "unknown") -> dict:
    opts: dict = {
        # Prefer an audio-only stream when the site offers one - smaller and faster.
        "format": "bestaudio/best",
        "outtmpl": str(workdir / "source.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "no_color": True,          # keep ANSI escapes out of API error strings
        "socket_timeout": settings.ytdlp_socket_timeout,
        "retries": settings.ytdlp_retries,
        "ffmpeg_location": str(Path(ffmpeg_path()).parent),
        "restrictfilenames": True,
        "overwrites": True,
    }
    # Instagram and TikTok both require a logged-in session - no cookies, no
    # media. The cookie file is auto-discovered, so dropping cookies.txt in the
    # project root is enough.
    cookiefile = settings.resolved_cookiefile
    if cookiefile:
        opts["cookiefile"] = cookiefile
        log.debug("Using cookie file for %s: %s", platform, cookiefile)
    elif settings.ytdlp_cookies_from_browser:
        opts["cookiesfrombrowser"] = (settings.ytdlp_cookies_from_browser,)
    return opts


_LOGIN_WALL_HINTS = (
    "login required", "log in", "rate-limit", "rate limit", "429",
    "restricted video", "private", "sign in", "cookies", "not available",
    "403", "forbidden", "bot", "confirm you", "sign-in",
)

# yt-dlp colourises its errors for a terminal. Those escape codes are noise once
# the message is on its way to a JSON response and a browser.
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _clean_error(msg: str) -> str:
    return _ANSI.sub("", msg).replace("ERROR:", "").strip()


def fetch_from_url(url: str, workdir: Path | None = None) -> MediaAsset:
    import yt_dlp

    workdir = workdir or new_workdir()
    platform = detect_platform(url)
    opts = _ytdlp_options(workdir, platform)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:
        msg = _clean_error(str(exc))
        low = msg.lower()
        if any(h in low for h in _LOGIN_WALL_HINTS):
            using_cookies = bool(
                settings.resolved_cookiefile or settings.ytdlp_cookies_from_browser
            )
            if using_cookies:
                detail = (
                    "Cookies are configured but were still rejected. They may be stale - "
                    "re-export them, and make sure you are logged in to "
                    f"{platform} in that browser."
                )
            else:
                detail = (
                    "No cookies are configured. Run 'python scripts/setup_cookies.py' "
                    "for a guided fix, or just upload the video file instead."
                )
            raise AcquisitionError(
                f"{platform.title()} refused this download - it requires a logged-in "
                f"session. {detail}  [{platform} said: {msg}]"
            ) from exc
        raise AcquisitionError(f"Download failed for {url}: {msg}") from exc

    if info is None:
        raise AcquisitionError(f"yt-dlp returned no metadata for {url}")
    if "entries" in info:
        entries = [e for e in info.get("entries") or [] if e]
        if not entries:
            raise AcquisitionError(f"No downloadable media found at {url}")
        info = entries[0]

    downloaded = _largest_file(workdir)
    if downloaded is None:
        raise AcquisitionError(f"yt-dlp reported success but produced no file for {url}")

    return MediaAsset(
        path=downloaded,
        source_kind="url",
        source_ref=url,
        platform=platform,
        title=(info.get("title") or "")[:500],
        uploader=(info.get("uploader") or info.get("channel") or "")[:200],
        meta={
            "webpage_url": info.get("webpage_url"),
            "ext": info.get("ext"),
            "reported_duration": info.get("duration"),
            "view_count": info.get("view_count"),
            "description": (info.get("description") or "")[:2000],
        },
    )


def _largest_file(workdir: Path) -> Path | None:
    files = [p for p in workdir.iterdir() if p.is_file() and p.stat().st_size > 0]
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_size, reverse=True)
    return files[0]


# --------------------------------------------------------------------------- #
# Direct CDN URL (browser extension path)
# --------------------------------------------------------------------------- #
_SAFE_HEADERS = {"referer", "user-agent", "origin", "accept", "accept-language"}


def fetch_direct(
    url: str,
    headers: dict[str, str] | None = None,
    workdir: Path | None = None,
    source_page: str = "",
) -> MediaAsset:
    """Stream an already-resolved media URL straight to disk."""
    workdir = workdir or new_workdir()
    clean = {k: v for k, v in (headers or {}).items() if k.lower() in _SAFE_HEADERS}
    clean.setdefault("User-Agent", "Mozilla/5.0")

    ext = Path(urlparse(url).path).suffix or ".mp4"
    if not re.fullmatch(r"\.[A-Za-z0-9]{1,5}", ext):
        ext = ".mp4"
    target = workdir / f"source{ext}"
    limit = settings.max_upload_mb * 1024 * 1024
    written = 0

    try:
        with httpx.stream(
            "GET", url, headers=clean, follow_redirects=True, timeout=60.0
        ) as r:
            r.raise_for_status()
            with target.open("wb") as fh:
                for chunk in r.iter_bytes(chunk_size=262_144):
                    written += len(chunk)
                    if written > limit:
                        raise AcquisitionError(
                            f"Media exceeds the {settings.max_upload_mb} MB limit."
                        )
                    fh.write(chunk)
    except AcquisitionError:
        raise
    except Exception as exc:
        raise AcquisitionError(f"Direct fetch failed: {exc}") from exc

    if written == 0:
        raise AcquisitionError("Direct fetch produced an empty file.")

    return MediaAsset(
        path=target,
        source_kind="direct",
        source_ref=source_page or url,
        platform=detect_platform(source_page or url),
        meta={"bytes": written, "cdn_url": url[:500]},
    )


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #
def register_upload(saved_path: Path, original_name: str) -> MediaAsset:
    return MediaAsset(
        path=saved_path,
        source_kind="upload",
        source_ref=original_name,
        platform="upload",
        meta={"bytes": saved_path.stat().st_size},
    )
