"""Data types whose JSON form is the contract in docs/ML_CONTRACT.md."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

Emphasis = Literal["normal", "strong", "low_confidence"]
GenerationSource = Literal["model", "template", "mock"]


@dataclass(frozen=True)
class Segment:
    label: str
    start_seconds: float
    end_seconds: float
    confidence: float | None = None
    alternatives: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class Limits:
    min_seconds: float = 0.5
    max_seconds: float = 10.0
    max_signs: int = 8


@dataclass(frozen=True)
class RecognitionResult:
    duration_seconds: float
    frames_decoded: int
    frames_used: int
    fps: float
    segments: list[Segment]
    overall_confidence: float | None
    low_confidence: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Token:
    text: str
    segment_index: int | None
    emphasis: Emphasis = "normal"


@dataclass(frozen=True)
class GenerationResult:
    text: str
    tokens: list[Token]
    source: GenerationSource
    constrained: bool
    rejected_reason: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def segment_from_dict(d: dict) -> Segment:
    return Segment(
        label=str(d["label"]),
        start_seconds=float(d["start_seconds"]),
        end_seconds=float(d["end_seconds"]),
        confidence=None if d.get("confidence") is None else float(d["confidence"]),
        alternatives=list(d.get("alternatives") or []),
    )
