"""Environment configuration. Every key is listed in ml-service/.env.example."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _float(name: str, default: float | None) -> float | None:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    internal_token: str
    mock: bool
    mock_delay_ms: int
    model_dir: Path
    max_clip_bytes: int
    low_confidence_threshold: float | None
    sign_language: str
    gen_backend: str
    gen_base_url: str
    gen_model: str
    gen_api_key: str
    gen_timeout_s: float
    gen_max_tokens: int
    gen_disable_thinking: bool

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get
        token = env("ML_INTERNAL_TOKEN", "").strip()
        if not token:
            raise RuntimeError("ML_INTERNAL_TOKEN must be set (see ml-service/.env.example)")
        return cls(
            internal_token=token,
            mock=env("ML_MOCK", "0") == "1",
            mock_delay_ms=int(env("ML_MOCK_DELAY_MS", "0")),
            model_dir=Path(env("ML_MODEL_DIR", "./models")),
            max_clip_bytes=int(env("ML_MAX_CLIP_BYTES", str(20 * 1024 * 1024))),
            low_confidence_threshold=_float("ML_LOW_CONFIDENCE_THRESHOLD", None),
            sign_language=env("ML_SIGN_LANGUAGE", "ase"),
            gen_backend=env("GEN_BACKEND", "template"),
            gen_base_url=env("GEN_BASE_URL", "http://127.0.0.1:8002/v1"),
            gen_model=env("GEN_MODEL", ""),
            gen_api_key=env("GEN_API_KEY", ""),
            gen_timeout_s=float(env("GEN_TIMEOUT_S", "20")),
            gen_max_tokens=int(env("GEN_MAX_TOKENS", "96")),
            gen_disable_thinking=env("GEN_DISABLE_THINKING", "1") == "1",
        )
