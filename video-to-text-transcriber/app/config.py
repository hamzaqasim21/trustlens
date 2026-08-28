"""Central configuration. Everything is overridable via .env or environment variables."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
    )

    # ---------- service ----------
    app_name: str = "TrustLens Video-to-Text Transcriber"
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "*"

    # ---------- storage ----------
    data_dir: Path = BASE_DIR / "data"
    database_url: str = ""  # blank -> sqlite file under data_dir

    # ---------- ASR backend ----------
    # local  = run Whisper on this machine
    # remote = forward to another TrustLens transcriber (e.g. free Colab/Kaggle GPU)
    asr_backend: Literal["local", "remote"] = "local"
    remote_asr_url: str = ""
    remote_asr_token: str = ""

    # Whisper checkpoint. Accepts a size name (tiny/base/small/medium/large-v3)
    # or any CTranslate2-converted HuggingFace repo id, e.g. a fine-tuned Urdu model.
    asr_model: str = "small"
    asr_device: Literal["auto", "cpu", "cuda"] = "auto"
    asr_compute_type: str = "auto"          # auto -> int8 on CPU, float16 on GPU
    asr_cpu_threads: int = 0                # 0 -> autodetect physical cores
    asr_beam_size: int = 5
    asr_download_root: Path | None = None

    # ---------- decoding quality / anti-hallucination ----------
    vad_enabled: bool = True
    vad_threshold: float = 0.5
    vad_min_silence_ms: int = 500
    vad_speech_pad_ms: int = 200
    # Whisper loops on repeated text when it conditions on its own prior output.
    # Social clips are short and musical, so we keep this OFF by default.
    condition_on_previous_text: bool = False
    no_speech_threshold: float = 0.6
    log_prob_threshold: float = -1.0
    compression_ratio_threshold: float = 2.4
    word_timestamps: bool = True

    # ---------- language policy ----------
    # Whisper frequently tags Pakistani Urdu speech as Hindi (`hi`) because the two
    # are near-identical when spoken. Our domain is Pakistani content, so we correct it.
    urdu_bias_enabled: bool = True
    urdu_bias_min_prob: float = 0.15        # if `ur` scores at least this, prefer it over `hi`
    lang_detect_windows: int = 3            # probe N windows across the clip, then vote
    allowed_languages: str = "ur,en,hi,pa,ps,sd,ar"

    # ---------- audio conditioning ----------
    audio_denoise: Literal["none", "light", "aggressive"] = "light"
    audio_sample_rate: int = 16000

    # ---------- limits ----------
    max_duration_sec: int = 900             # 15 min
    max_upload_mb: int = 200
    job_workers: int = 1                    # ASR is CPU-bound; >1 thrashes a 2-core box
    job_retention_hours: int = 72
    keep_media_files: bool = False

    # ---------- media acquisition ----------
    ytdlp_cookies_from_browser: str = ""    # e.g. "chrome", "edge", "firefox"
    ytdlp_cookiefile: str = ""
    ytdlp_socket_timeout: int = 30
    ytdlp_retries: int = 3

    # ---------- OCR fallback ----------
    ocr_enabled: bool = False               # opt-in: pulls PyTorch
    ocr_languages: str = "ur,en"
    ocr_frame_count: int = 12
    ocr_min_confidence: float = 0.35
    # Auto-run OCR when the audio transcript is too weak to be useful
    ocr_auto_fallback: bool = True
    ocr_fallback_min_chars: int = 40
    ocr_fallback_min_confidence: float = 0.45

    # ---------- caching ----------
    cache_enabled: bool = True

    @field_validator("data_dir", mode="after")
    @classmethod
    def _mk(cls, v: Path) -> Path:
        v.mkdir(parents=True, exist_ok=True)
        return v

    # ----- derived -----
    @property
    def media_dir(self) -> Path:
        p = self.data_dir / "media"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def models_dir(self) -> Path:
        p = self.asr_download_root or (self.data_dir / "models")
        Path(p).mkdir(parents=True, exist_ok=True)
        return Path(p)

    @property
    def resolved_cookiefile(self) -> str:
        """Find a Netscape cookies.txt without needing it configured.

        Checked in order: the explicit YTDLP_COOKIEFILE setting, then a few
        conventional filenames in the project root and data/. Dropping the
        exported file into the project folder is enough - no .env edit needed.
        """
        if self.ytdlp_cookiefile:
            p = Path(self.ytdlp_cookiefile).expanduser()
            return str(p) if p.exists() else ""

        for name in ("cookies.txt", "instagram_cookies.txt"):
            for folder in (BASE_DIR, self.data_dir):
                candidate = folder / name
                if candidate.exists() and candidate.stat().st_size > 0:
                    return str(candidate)
        return ""

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'transcriber.db').as_posix()}"

    @property
    def allowed_language_list(self) -> list[str]:
        return [x.strip() for x in self.allowed_languages.split(",") if x.strip()]

    @property
    def ocr_language_list(self) -> list[str]:
        return [x.strip() for x in self.ocr_languages.split(",") if x.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    def resolve_device(self) -> tuple[str, str]:
        """Pick (device, compute_type). int8 on CPU keeps large models in RAM budget."""
        device = self.asr_device
        if device == "auto":
            device = "cuda" if _cuda_available() else "cpu"
        compute = self.asr_compute_type
        if compute == "auto":
            compute = "float16" if device == "cuda" else "int8"
        return device, compute

    def resolve_cpu_threads(self) -> int:
        if self.asr_cpu_threads > 0:
            return self.asr_cpu_threads
        return max(1, (os.cpu_count() or 2))


def _cuda_available() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
