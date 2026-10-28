"""ASL alphabet from hand landmarks: one hand pose → one letter, then held poses → spelling.

Why per-frame: a fingerspelled letter is a hand *shape* (J and Z add a small motion), so
21 hand points are enough, and it works whether or not the face and body are in view.
Features are translation-, scale- and handedness-normalised (left hands are mirrored),
but not rotation-normalised: orientation separates letters such as U/H and K/P.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .landmarks import LEFT_HAND, RIGHT_HAND

LETTERS = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
FEATURE_VERSION = 1
N_FEATURES = 21 * 3


def hand_features(points: np.ndarray, is_left: bool) -> np.ndarray:
    """[21, 3] image-space hand landmarks → [63] normalised vector (NaN in → NaN out)."""
    p = points.astype(np.float32).copy()
    if is_left:
        p[:, 0] = -p[:, 0]  # mirror to a right hand
    p = p - p[0]  # wrist at the origin
    scale = np.linalg.norm(p[9, :2])  # wrist → middle-finger knuckle
    if not np.isfinite(scale) or scale < 1e-6:
        return np.full(N_FEATURES, np.nan, np.float32)
    return (p / scale).reshape(-1)


def track_hands(xyz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per frame, the features of the signing hand (the one present in more frames).
    Returns (features [frames, 63] with NaN rows where no hand, present [frames] bool)."""
    left, right = xyz[:, LEFT_HAND[0]:LEFT_HAND[1]], xyz[:, RIGHT_HAND[0]:RIGHT_HAND[1]]
    has_l, has_r = np.isfinite(left).all(axis=(1, 2)), np.isfinite(right).all(axis=(1, 2))
    prefer_left = has_l.sum() > has_r.sum()
    feats = np.full((len(xyz), N_FEATURES), np.nan, np.float32)
    for f in range(len(xyz)):
        use_left = has_l[f] and (prefer_left or not has_r[f])
        if use_left or has_r[f]:
            feats[f] = hand_features(left[f] if use_left else right[f], is_left=use_left)
    present = np.isfinite(feats).all(axis=1)
    return feats, present


@dataclass
class LetterModelConfig:
    hidden: int = 256
    dropout: float = 0.2
    feature_version: int = FEATURE_VERSION


def build_mlp(cfg: LetterModelConfig):
    import mlx.nn as nn

    return nn.Sequential(nn.Linear(N_FEATURES, cfg.hidden), nn.GELU(), nn.Dropout(cfg.dropout),
                         nn.Linear(cfg.hidden, cfg.hidden), nn.GELU(), nn.Dropout(cfg.dropout),
                         nn.Linear(cfg.hidden, len(LETTERS)))


def save(model, cfg: LetterModelConfig, out_dir: Path, metrics: dict | None = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_weights(str(out_dir / "weights.safetensors"))
    (out_dir / "config.json").write_text(json.dumps(asdict(cfg), indent=2))
    if metrics is not None:
        (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))


_erf = np.vectorize(math.erf, otypes=[np.float32])


def _gelu(x: np.ndarray) -> np.ndarray:
    """Exact GELU, matching mlx.nn.GELU()."""
    return 0.5 * x * (1.0 + _erf(x / math.sqrt(2.0)))


@dataclass
class SpelledLetter:
    char: str
    start_seconds: float
    end_seconds: float
    confidence: float


class LetterReader:
    """Classifies every frame, then keeps letters held steadily for at least `min_hold`."""

    name = "asl-letters-mlp"

    # Defaults tuned on the alphabet validation video (validation/validate_letters.py):
    # hold a letter ~0.5 s; the same letter again within 1 s is one letter unless the hand
    # dropped out of view in between.
    def __init__(self, model_dir: Path, min_hold: float = 0.5, min_confidence: float = 0.6, merge_gap: float = 1.0):
        import mlx.core as mx

        cfg = LetterModelConfig(**json.loads((model_dir / "config.json").read_text()))
        if cfg.feature_version != FEATURE_VERSION:
            raise ValueError(f"letter model in {model_dir} uses feature version {cfg.feature_version}")
        # Inference runs in NumPy: the server calls us from worker threads, and MLX streams
        # belong to the thread that created them. The MLP is tiny, so this costs nothing.
        w = mx.load(str(model_dir / "weights.safetensors"))
        self._layers = [(np.array(w[f"layers.{i}.weight"]).T, np.array(w[f"layers.{i}.bias"])) for i in (0, 3, 6)]
        self.min_hold, self.min_confidence, self.merge_gap = min_hold, min_confidence, merge_gap
        self.version = (model_dir / "VERSION").read_text().strip() if (model_dir / "VERSION").exists() else model_dir.name

    def frame_probabilities(self, feats: np.ndarray) -> np.ndarray:
        h = np.nan_to_num(feats, nan=0.0).astype(np.float32)
        for i, (weight, bias) in enumerate(self._layers):
            h = h @ weight + bias
            if i < len(self._layers) - 1:
                h = _gelu(h)
        h = h - h.max(axis=-1, keepdims=True)
        e = np.exp(h)
        return e / e.sum(axis=-1, keepdims=True)

    def read(self, xyz: np.ndarray, times: np.ndarray) -> list[SpelledLetter]:
        feats, present = track_hands(xyz)
        if not present.any():
            return []
        probs = np.zeros((len(feats), len(LETTERS)), np.float32)
        probs[present] = self.frame_probabilities(feats[present])
        best, conf = probs.argmax(axis=1), probs.max(axis=1)
        steady = present & (conf >= self.min_confidence)
        out: list[SpelledLetter] = []
        f = 0
        while f < len(best):
            if not steady[f]:
                f += 1
                continue
            g = f
            while g + 1 < len(best) and steady[g + 1] and best[g + 1] == best[f]:
                g += 1
            if times[g] - times[f] >= self.min_hold:
                letter = LETTERS[int(best[f])]
                c = float(conf[f:g + 1].mean())
                # The same letter twice in a row only counts if the hand clearly let go between.
                last_end = int(np.searchsorted(times, out[-1].end_seconds)) if out else 0
                hand_left = out and not present[last_end:f].all()
                if out and out[-1].char == letter and times[f] - out[-1].end_seconds < self.merge_gap and not hand_left:
                    out[-1].end_seconds, out[-1].confidence = float(times[g]), max(out[-1].confidence, c)
                else:
                    out.append(SpelledLetter(letter, float(times[f]), float(times[g]), c))
            f = g + 1
        return out


class LetterRecognizer:
    """Recognizer-shaped wrapper: clip → letters as RecognitionResult segments."""

    name = "asl-letters"

    def __init__(self, reader: LetterReader, extractor):
        self.reader, self.extractor = reader, extractor
        self.version = reader.version

    def recognize(self, clip_path: Path, *, sign_language: str, limits) -> "RecognitionResult":
        from ..schemas import RecognitionResult, Segment
        from .features import hands_present
        from .islr import ClipError
        from .landmarks import UndecodableClip

        try:
            track = self.extractor.extract(clip_path)
        except UndecodableClip as e:
            raise ClipError("undecodable_clip", f"The video could not be decoded: {e}.") from e
        if track.duration_seconds > limits.max_seconds + 0.5:
            raise ClipError("clip_too_long", f"The clip is {track.duration_seconds:.1f} s long. Record {limits.max_seconds:g} seconds or less.",
                            {"max_seconds": limits.max_seconds, "actual_seconds": round(track.duration_seconds, 2)})
        letters = self.reader.read(track.xyz, track.times)[: max(limits.max_signs, 1) * 4]
        segments = [Segment(l.char, round(l.start_seconds, 3), round(l.end_seconds, 3), round(l.confidence, 4)) for l in letters]
        overall = round(float(np.mean([s.confidence for s in segments])), 4) if segments else None
        return RecognitionResult(duration_seconds=round(track.duration_seconds, 3), frames_decoded=track.frames_decoded,
                                 frames_used=track.frames_used, fps=round(track.fps, 2), segments=segments,
                                 overall_confidence=overall, low_confidence=overall is None or overall < 0.7,
                                 hands_seen=round(float(hands_present(track.xyz).mean()) if len(track.times) else 0.0, 3))


def spelled_generation(segments) -> "GenerationResult":
    """Letters need no language model: the word is the letters themselves."""
    from ..schemas import GenerationResult, Token

    word = "".join(s.label for s in segments)
    return GenerationResult(text=word, tokens=[Token(word, None, "strong")], source="fingerspelling", constrained=True)
