"""Images of A–Z handshapes → normalised hand-landmark features.

    python training/letters/prepare.py --parquet data/letters/train-0.parquet --out data/letters/features.npz

Uses MediaPipe HandLandmarker (IMAGE mode). Images where no hand is found (drawings,
blurred crops) are skipped and counted.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from visualiser_ml.recognition.letters import hand_features  # noqa: E402


def main(argv=None):
    import cv2
    import mediapipe as mp
    import pyarrow.parquet as pq
    from mediapipe.tasks.python import BaseOptions, vision

    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--hand-model", type=Path, default=ROOT / "models/mediapipe/hand_landmarker.task")
    args = ap.parse_args(argv)

    table = pq.read_table(args.parquet).to_pydict()
    opts = vision.HandLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(args.hand_model)),
                                        num_hands=1, min_hand_detection_confidence=0.3)
    X, y, skipped = [], [], 0
    with vision.HandLandmarker.create_from_options(opts) as det:
        for i, (img, label) in enumerate(zip(table["image"], table["label"])):
            bgr = cv2.imdecode(np.frombuffer(img["bytes"], np.uint8), cv2.IMREAD_COLOR)
            if bgr is None:
                skipped += 1
                continue
            res = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
            if not res.hand_landmarks:
                skipped += 1
                continue
            pts = np.array([(p.x, p.y, p.z) for p in res.hand_landmarks[0]], np.float32)
            # HandLandmarker labels handedness as if the image were mirrored (selfie); flip it.
            is_left = res.handedness[0][0].category_name == "Right"
            X.append(hand_features(pts, is_left))
            y.append(int(label))
            if i % 2000 == 0:
                print(f"{i}/{len(table['label'])}", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, X=np.stack(X), y=np.array(y, np.int32))
    print(f"{len(y)} hands kept, {skipped} images skipped (no hand found) -> {args.out}")


if __name__ == "__main__":
    main()
