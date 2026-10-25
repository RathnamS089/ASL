"""Sign recognition (owned by the Recognition workstream). Only the interface lives here for now."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..schemas import Limits, RecognitionResult


class Recognizer(Protocol):
    name: str
    version: str

    def recognize(self, clip_path: Path, *, sign_language: str, limits: Limits) -> RecognitionResult: ...
