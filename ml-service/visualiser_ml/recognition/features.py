"""Landmarks → fixed-size model input. Used by BOTH training (ISLR parquet) and serving
(uploaded clips), so the two can never drift apart. Bump FEATURE_VERSION on any change;
a model trained on another version refuses to load.
"""
from __future__ import annotations

import warnings

import numpy as np

from .landmarks import LEFT_HAND, POSE, RIGHT_HAND

FEATURE_VERSION = 1
T = 32  # frames after time-normalisation
VELOCITY_SCALE = 5.0  # per-frame motion is ~30x smaller than position; bring it into range

# Face mesh indices (0-467): lips, eyebrows, eye corners, nose. Facial movement is part of
# sign-language grammar; these points describe expression, not identity.
LIPS = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 146, 91, 181, 84, 17, 314, 405, 321, 375,
        78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308]
BROW_L, BROW_R = [70, 63, 105, 66, 107], [336, 296, 334, 293, 300]
EYES_L, EYES_R = [33, 133], [362, 263]
NOSE = [1, 4]
FACE_POINTS = LIPS + BROW_L + BROW_R + EYES_L + EYES_R + NOSE
FACE_MIRROR = LIPS + BROW_R + BROW_L + EYES_R + EYES_L + NOSE  # what each slot becomes when mirrored

# Pose (0-32): nose, shoulders, elbows, wrists.
POSE_POINTS = [0, 11, 12, 13, 14, 15, 16]
POSE_MIRROR = [0, 12, 11, 14, 13, 16, 15]

N_POINTS = 21 + 21 + len(POSE_POINTS) + len(FACE_POINTS)
FEATURE_DIM = N_POINTS * 2 * 2 + 2  # xy positions + xy velocities + 2 hand-presence flags


def _hand(xyz: np.ndarray, span: tuple[int, int]) -> np.ndarray:
    return xyz[:, span[0]:span[1], :2]


def dominant_is_left(xyz: np.ndarray) -> bool:
    """The hand seen in more frames is treated as dominant (ISLR signers use either)."""
    left = np.isfinite(_hand(xyz, LEFT_HAND)).all(axis=(1, 2)).sum()
    right = np.isfinite(_hand(xyz, RIGHT_HAND)).all(axis=(1, 2)).sum()
    return bool(left > right)


def select(xyz: np.ndarray) -> np.ndarray:
    """[frames, 543, 3] → [frames, N_POINTS, 2] in canonical (right-dominant) orientation."""
    mirror = dominant_is_left(xyz)
    pose = xyz[:, [POSE[0] + i for i in (POSE_MIRROR if mirror else POSE_POINTS)], :2]
    face = xyz[:, FACE_MIRROR if mirror else FACE_POINTS, :2]
    dom, other = (_hand(xyz, LEFT_HAND), _hand(xyz, RIGHT_HAND)) if mirror else (_hand(xyz, RIGHT_HAND), _hand(xyz, LEFT_HAND))
    pts = np.concatenate([dom, other, pose, face], axis=1).astype(np.float32)
    if mirror:
        pts[..., 0] = 1.0 - pts[..., 0]
    return pts


def normalise(pts: np.ndarray) -> np.ndarray:
    """Centre on the shoulders (or the face), scale by shoulder width, so position in the
    frame and distance from the camera do not matter."""
    off = 42  # first pose slot
    l_sh, r_sh = pts[:, off + 1], pts[:, off + 2]
    with warnings.catch_warnings():  # all-NaN columns (nobody in frame) are expected
        warnings.simplefilter("ignore", RuntimeWarning)
        centre = np.nanmean((l_sh + r_sh) / 2, axis=0)
        width = np.nanmean(np.linalg.norm(l_sh - r_sh, axis=-1))
        if not np.isfinite(centre).all():
            centre = np.nanmean(pts[:, 49:], axis=(0, 1))  # face points
        if not np.isfinite(centre).all():
            centre = np.nanmean(pts, axis=(0, 1)) if np.isfinite(pts).any() else np.zeros(2, np.float32)
        if not (np.isfinite(width) and width > 1e-3):
            spread = np.nanstd(pts) if np.isfinite(pts).any() else 0.0
            width = spread * 2 if spread > 1e-3 else 1.0
    return ((pts - centre) / width).astype(np.float32)


def resample(arr: np.ndarray, length: int = T) -> np.ndarray:
    n = len(arr)
    if n == 0:
        return np.full((length,) + arr.shape[1:], np.nan, dtype=np.float32)
    idx = np.round(np.linspace(0, n - 1, length)).astype(int)
    return arr[idx]


def featurize(xyz: np.ndarray) -> np.ndarray:
    """[frames, 543, 3] (NaN = missing) → [T, FEATURE_DIM] float32, no NaNs."""
    pts = resample(normalise(select(xyz)))
    present = np.stack([np.isfinite(pts[:, 0:21]).all(axis=(1, 2)), np.isfinite(pts[:, 21:42]).all(axis=(1, 2))], axis=1)
    vel = np.diff(pts, axis=0, prepend=pts[:1]) * VELOCITY_SCALE
    feats = np.concatenate([pts.reshape(T, -1), vel.reshape(T, -1)], axis=1)
    feats = np.nan_to_num(feats, nan=0.0, posinf=0.0, neginf=0.0)
    return np.concatenate([feats, present.astype(np.float32)], axis=1).astype(np.float32)


def hands_present(xyz: np.ndarray) -> np.ndarray:
    """[frames] bool: at least one hand detected."""
    return np.isfinite(_hand(xyz, LEFT_HAND)).all(axis=(1, 2)) | np.isfinite(_hand(xyz, RIGHT_HAND)).all(axis=(1, 2))


assert FEATURE_DIM == 2 * 2 * N_POINTS + 2
