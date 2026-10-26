"""Split a clip into candidate sign segments using hand presence and hand motion.

ISLR teaches the model isolated signs, so a clip with several signs is cut into pieces
first. Rules (deliberately simple, tuned on nothing yet; measure before trusting):
1. A segment is a run of frames where a hand is visible. Gaps shorter than MERGE_GAP
   seconds (a hand briefly lost by the tracker) are bridged.
2. Runs shorter than MIN_SIGN seconds are noise and dropped.
3. A run longer than SPLIT_OVER seconds probably holds several signs; it is split at the
   slowest moments of the dominant hand, keeping every piece at least MIN_PIECE long.
"""
from __future__ import annotations

import warnings

import numpy as np

from .features import hands_present
from .landmarks import LEFT_HAND, RIGHT_HAND

MERGE_GAP = 0.25
MIN_SIGN = 0.3
SPLIT_OVER = 2.4
MIN_PIECE = 0.6


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    runs, start = [], None
    for i, on in enumerate(mask):
        if on and start is None:
            start = i
        elif not on and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    return runs


def _hand_speed(xyz: np.ndarray, times: np.ndarray) -> np.ndarray:
    wrists = np.stack([xyz[:, LEFT_HAND[0], :2], xyz[:, RIGHT_HAND[0], :2]], axis=1)  # [f, 2, 2]
    step = np.linalg.norm(np.diff(wrists, axis=0), axis=-1)  # [f-1, 2]
    dt = np.maximum(np.diff(times), 1e-3)[:, None]
    with warnings.catch_warnings():  # frames with no hands give all-NaN rows
        warnings.simplefilter("ignore", RuntimeWarning)
        speed = np.nanmax(np.where(np.isfinite(step), step / dt, np.nan), axis=1)
    speed = np.nan_to_num(speed, nan=0.0)
    return np.concatenate([[speed[0] if len(speed) else 0.0], speed])


def segment(xyz: np.ndarray, times: np.ndarray, max_signs: int = 8) -> list[tuple[int, int]]:
    """Returns [start, end) frame index pairs, in order."""
    n = len(times)
    if n == 0:
        return []
    present = hands_present(xyz)
    runs = _runs(present)
    merged: list[list[int]] = []
    for s, e in runs:
        if merged and times[s] - times[merged[-1][1] - 1] <= MERGE_GAP:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    runs = [(s, e) for s, e in merged if times[e - 1] - times[s] >= MIN_SIGN]

    speed = _hand_speed(xyz, times)
    out: list[tuple[int, int]] = []
    for s, e in runs:
        out.extend(_split(s, e, times, speed))
    return out[:max_signs]


def _split(s: int, e: int, times: np.ndarray, speed: np.ndarray) -> list[tuple[int, int]]:
    if times[e - 1] - times[s] <= SPLIT_OVER:
        return [(s, e)]
    # Smooth speed, then cut at the slowest interior frame that leaves both sides long enough.
    k = 3
    smooth = np.convolve(speed[s:e], np.ones(k) / k, mode="same")
    order = np.argsort(smooth)
    for i in order:
        cut = s + int(i)
        if times[cut] - times[s] >= MIN_PIECE and times[e - 1] - times[cut] >= MIN_PIECE:
            return _split(s, cut, times, speed) + _split(cut, e, times, speed)
    return [(s, e)]
