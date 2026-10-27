"""Fingerspelling (the ASL alphabet): landmarks → letters.

Model: Skunk0/openglasses-fingerspelling-ctc (Apache-2.0), a CTC model trained on Google's
ASL Fingerspelling corpus (CC-BY 4.0), shipped as Core ML. It reads the same 543-landmark
Holistic layout as the sign recognizer, so the same extractor feeds both.

Contract (from its model card): input `features` (1, 768, 1629) = up to 768 frames × 543
landmarks × xyz, "per-window standardised, NaN→0, zero-padded", plus `mask` (1, 768);
output (1, 384, 62) CTC logits at stride 2. Class 0 is blank, 1..59 map through vocab.txt,
the last two are auxiliary. "Per-window standardised" is not specified further; we
standardise each coordinate axis over the window's detected points, which scored best on
the alphabet validation video (validation/validate_alphabet.py).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

WINDOW = 768
STRIDE = 2


@dataclass
class Letter:
    char: str
    start_seconds: float
    end_seconds: float
    confidence: float


def standardise(xyz: np.ndarray, mode: str = "axis") -> np.ndarray:
    """[frames, 543, 3] with NaN → [frames, 1629] float32, NaN → 0."""
    x = xyz.astype(np.float32).copy()
    finite = np.isfinite(x)
    if finite.any():
        if mode == "axis":  # one mean/std per x, y, z over every detected point in the window
            for a in range(3):
                vals = x[..., a][finite[..., a]]
                if vals.size:
                    x[..., a] = (x[..., a] - vals.mean()) / (vals.std() + 1e-6)
        elif mode == "column":  # one mean/std per landmark coordinate
            mean = np.nanmean(np.where(finite, x, np.nan), axis=0)
            std = np.nanstd(np.where(finite, x, np.nan), axis=0)
            x = (x - np.nan_to_num(mean)) / (np.nan_to_num(std) + 1e-6)
        elif mode != "none":
            raise ValueError(mode)
    return np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0).reshape(len(x), -1)


class FingerspellingReader:
    name = "openglasses-fingerspelling-ctc"

    def __init__(self, model_dir: Path, standardise_mode: str = "axis"):
        import coremltools as ct

        self.model = ct.models.MLModel(str(model_dir / "Fingerspelling2P.mlpackage"))
        vocab = (model_dir / "vocab.txt").read_text(encoding="utf-8").split("\n")
        self.vocab = vocab[:60]  # index 0 = <blank>; 1..59 = symbols (index 1 is the space)
        self.mode = standardise_mode
        self.version = "1"

    def logits(self, xyz: np.ndarray) -> np.ndarray:
        """[frames ≤ 768, 543, 3] → [ceil(frames/2), 62] log-probabilities."""
        n = min(len(xyz), WINDOW)
        feats = np.zeros((1, WINDOW, 543 * 3), np.float32)
        mask = np.zeros((1, WINDOW), np.float32)
        feats[0, :n] = standardise(xyz[:n], self.mode)
        mask[0, :n] = 1
        out = next(iter(self.model.predict({"features": feats, "mask": mask}).values()))
        z = np.asarray(out, dtype=np.float64)[0, : (n + STRIDE - 1) // STRIDE]
        z = z - z.max(axis=-1, keepdims=True)
        return z - np.log(np.exp(z).sum(axis=-1, keepdims=True))

    def read(self, xyz: np.ndarray, times: np.ndarray, min_confidence: float = 0.0) -> list[Letter]:
        """Greedy CTC decode with per-letter timing; windows longer than 768 frames are chunked."""
        letters: list[Letter] = []
        for start in range(0, max(len(xyz), 1), WINDOW):
            chunk = xyz[start:start + WINDOW]
            if not len(chunk):
                break
            logp = self.logits(chunk)
            best = logp.argmax(axis=-1)
            prev = 0
            for step, k in enumerate(best):
                if k != prev and 0 < k < len(self.vocab):
                    f0 = min(start + step * STRIDE, len(times) - 1)
                    f1 = min(f0 + STRIDE, len(times) - 1)
                    conf = float(np.exp(logp[step, k]))
                    if conf >= min_confidence:
                        letters.append(Letter(self.vocab[k], float(times[f0]), float(times[f1]), conf))
                prev = k
        return letters


def letters_to_text(letters: list[Letter]) -> str:
    return "".join(l.char for l in letters).strip()
