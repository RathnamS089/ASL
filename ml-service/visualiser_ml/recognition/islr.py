"""The real Recognizer: clip → landmarks → segments → ISLR classifier.

Two interchangeable classifiers, picked by what is in the model directory:
- TFLiteClassifier: `model.tflite` + `sign_to_prediction_index_map.json`, e.g. the
  1st-place Kaggle ISLR model (huggingface.co/sign/kaggle-asl-signs-1st-place). It takes
  raw [frames, 543, 3] landmarks and returns 250 logits.
- MlxClassifier: `weights.safetensors` + `config.json` + `labels.json` from
  training/islr/train.py. It takes our [T, FEATURE_DIM] features.
"""
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


class Classifier(Protocol):
    name: str
    version: str
    labels: list[str]
    target_fps: float

    def probabilities(self, segments: list[np.ndarray]) -> np.ndarray: ...  # [k, n_classes]


def _softmax(logits: np.ndarray) -> np.ndarray:
    z = logits - logits.max(axis=-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=-1, keepdims=True)


class TFLiteClassifier:
    """Raw-landmark TFLite model (the Kaggle ISLR submission format)."""

    target_fps = 30.0  # ISLR clips were recorded at phone frame rate

    def __init__(self, model_dir: Path):
        from ai_edge_litert.interpreter import Interpreter

        import json

        index = json.loads((model_dir / "sign_to_prediction_index_map.json").read_text())
        self.labels = [s for s, _ in sorted(index.items(), key=lambda kv: kv[1])]
        self._runner = Interpreter(model_path=str(model_dir / "model.tflite")).get_signature_runner()
        self.name = "islr-tflite"
        self.version = model_dir.name

    def probabilities(self, segments: list[np.ndarray]) -> np.ndarray:
        out = []
        for xyz in segments:  # one call per segment: the model takes a variable frame count
            logits = next(iter(self._runner(inputs=np.ascontiguousarray(xyz, dtype=np.float32)).values()))
            out.append(_softmax(np.asarray(logits, dtype=np.float64)))
        return np.stack(out)


class MlxClassifier:
    """Our own model from training/islr/train.py."""

    target_fps = 15.0

    def __init__(self, model_dir: Path):
        from .model import load  # MLX import stays out of module import time

        self.model, self.labels = load(model_dir)
        self.name = "islr-transformer"
        self.version = (model_dir / "VERSION").read_text().strip() if (model_dir / "VERSION").exists() else model_dir.name

    def probabilities(self, segments: list[np.ndarray]) -> np.ndarray:
        import mlx.core as mx

        feats = np.stack([featurize(xyz) for xyz in segments])
        return np.array(mx.softmax(self.model(mx.array(feats)), axis=-1))


def load_classifier(model_dir: Path) -> Classifier:
    if (model_dir / "model.tflite").is_file():
        return TFLiteClassifier(model_dir)
    if (model_dir / "weights.safetensors").is_file():
        return MlxClassifier(model_dir)
    raise FileNotFoundError(f"no model.tflite or weights.safetensors in {model_dir}")


def gloss(label: str) -> str:
    """ISLR labels are lower-case words ("TV", "after", "glasswindow") → upper-case glosses."""
    return label.strip().upper().replace(" ", "-").replace("_", "-")


class IslrRecognizer:
    # Frames of context kept on each side of a segment: signs start before the hands are
    # fully tracked, and the ISLR clips include a little lead-in.
    PAD_FRAMES = 3

    def __init__(self, model_dir: Path | Classifier, extractor: Extractor, min_sign_confidence: float = 0.25,
                 low_confidence_threshold: float = 0.5):
        self.classifier = load_classifier(model_dir) if isinstance(model_dir, Path) else model_dir
        self.name, self.version = self.classifier.name, self.classifier.version
        self.glosses = [gloss(l) for l in self.classifier.labels]
        self.extractor = extractor
        self.min_sign_confidence = min_sign_confidence
        self.low_confidence_threshold = low_confidence_threshold

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
            n = len(track.times)
            probs = self.classifier.probabilities(
                [track.xyz[max(0, s - self.PAD_FRAMES):min(n, e + self.PAD_FRAMES)] for s, e in spans])
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
