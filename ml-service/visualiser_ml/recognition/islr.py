"""The real Recognizer: clip → landmarks → segments → ISLR-trained classifier."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np

from ..schemas import Limits, RecognitionResult, Segment
from .features import featurize
from .landmarks import LandmarkTrack, UndecodableClip
from .segmenter import segment


class ClipError(Exception):
    """A clip the contract says to reject with 422 (code is the contract error code)."""

    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details or {}


class Extractor(Protocol):
    name: str

    def extract(self, clip_path: Path) -> LandmarkTrack: ...


def gloss(label: str) -> str:
    """ISLR labels are lower-case words ("TV", "after", "glasswindow") → upper-case glosses."""
    return label.strip().upper().replace(" ", "-").replace("_", "-")


class IslrRecognizer:
    name = "islr-transformer"

    def __init__(self, model_dir: Path, extractor: Extractor, min_sign_confidence: float = 0.25,
                 low_confidence_threshold: float = 0.5):
        from .model import load  # MLX import stays out of module import time

        self.model, labels = load(model_dir)
        self.glosses = [gloss(l) for l in labels]
        self.version = (model_dir / "VERSION").read_text().strip() if (model_dir / "VERSION").exists() else model_dir.name
        self.extractor = extractor
        self.min_sign_confidence = min_sign_confidence
        self.low_confidence_threshold = low_confidence_threshold

    def probabilities(self, feats: np.ndarray) -> np.ndarray:
        import mlx.core as mx

        logits = self.model(mx.array(feats))
        return np.array(mx.softmax(logits, axis=-1))

    def recognize(self, clip_path: Path, *, sign_language: str, limits: Limits,
                  include_alternatives: bool = False) -> RecognitionResult:
        try:
            track = self.extractor.extract(clip_path)
        except UndecodableClip as e:
            raise ClipError("undecodable_clip", f"The video could not be decoded: {e}.") from e
        if track.duration_seconds < limits.min_seconds:
            raise ClipError("clip_too_short", f"The clip is {track.duration_seconds:.1f} s long. Record at least {limits.min_seconds:g} s.",
                            {"min_seconds": limits.min_seconds, "actual_seconds": round(track.duration_seconds, 2)})
        if track.duration_seconds > limits.max_seconds + 0.5:
            raise ClipError("clip_too_long", f"The clip is {track.duration_seconds:.1f} s long. Record {limits.max_seconds:g} seconds or less.",
                            {"max_seconds": limits.max_seconds, "actual_seconds": round(track.duration_seconds, 2)})

        spans = segment(track.xyz, track.times, max_signs=limits.max_signs)
        segments: list[Segment] = []
        if spans:
            probs = self.probabilities(np.stack([featurize(track.xyz[s:e]) for s, e in spans]))
            for (s, e), p in zip(spans, probs):
                top = np.argsort(p)[::-1][:3]
                conf = float(p[top[0]])
                if conf < self.min_sign_confidence:
                    continue  # most likely not a sign in the vocabulary
                label = self.glosses[int(top[0])]
                start, end = float(track.times[s]), float(track.times[e - 1])
                if segments and segments[-1].label == label:  # one sign split in two
                    prev = segments.pop()
                    start, conf = prev.start_seconds, max(conf, prev.confidence or 0)
                alts = [{"label": self.glosses[int(i)], "confidence": round(float(p[i]), 4)} for i in top[1:]] if include_alternatives else []
                segments.append(Segment(label, round(start, 3), round(max(end, start), 3), round(conf, 4), alts))
        overall = round(float(np.mean([s.confidence for s in segments])), 4) if segments else None
        return RecognitionResult(
            duration_seconds=round(track.duration_seconds, 3),
            frames_decoded=track.frames_decoded,
            frames_used=track.frames_used,
            fps=round(track.fps, 2),
            segments=segments,
            overall_confidence=overall,
            low_confidence=overall is None or overall < self.low_confidence_threshold,
        )
