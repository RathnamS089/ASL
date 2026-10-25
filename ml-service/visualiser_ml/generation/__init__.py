"""Gloss-to-text generators. See docs/ML_CONTRACT.md and ml-service/MODEL_SELECTION.md."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ..schemas import GenerationResult, Segment


class Generator(Protocol):
    name: str
    version: str

    def generate(self, segments: Sequence[Segment], *, sign_language: str,
                 target_language: str = "en") -> GenerationResult: ...
