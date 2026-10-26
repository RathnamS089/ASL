"""Extract MediaPipe landmarks for a whole video once and cache them (validation only).

    python validation/extract.py data/youtube/N45u5W3rOBc.mp4 [--fps 30]

Writes <video>.landmarks.npz next to the video (git-ignored, like the video itself).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from visualiser_ml.recognition.landmarks import HolisticExtractor  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--fps", type=float, default=30.0)
    args = ap.parse_args(argv)
    out = args.video.with_suffix(".landmarks.npz")
    started = time.perf_counter()
    ex = HolisticExtractor(ROOT / "models" / "mediapipe" / "holistic_landmarker.task", target_fps=args.fps, max_seconds=1e9)
    track = ex.extract(args.video)
    np.savez_compressed(out, xyz=track.xyz, times=track.times, fps=track.fps)
    secs = time.perf_counter() - started
    hands = np.isfinite(track.xyz[:, 468:489, 0]).all(1) | np.isfinite(track.xyz[:, 522:543, 0]).all(1)
    print(f"{args.video.name}: {track.frames_used} frames over {track.duration_seconds:.0f} s, "
          f"hands visible in {hands.mean():.0%}, took {secs:.0f} s ({secs / max(track.frames_used, 1) * 1000:.1f} ms/frame) -> {out.name}")


if __name__ == "__main__":
    main()
