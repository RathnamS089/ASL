"""Turn the Google ISLR dataset (Kaggle "asl-signs") into model-ready features.

    python training/islr/prepare.py --data data/asl-signs --out data/islr-features [--signs 50] [--limit N]

Input layout (as downloaded from Kaggle):
    train.csv                         path, participant_id, sequence_id, sign
    train_landmark_files/<pid>/<seq>.parquet  frame, row_id, type, landmark_index, x, y, z (543 rows/frame)

Output: features.npy [N, T, FEATURE_DIM] float16, labels.npy, participants.npy, labels.json.
Uses exactly the serving feature code (visualiser_ml.recognition.features).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from visualiser_ml.recognition.features import FEATURE_DIM, T, featurize  # noqa: E402
from visualiser_ml.recognition.landmarks import N_LANDMARKS  # noqa: E402


def load_parquet(path: Path) -> np.ndarray:
    import pyarrow.parquet as pq

    table = pq.read_table(path, columns=["frame", "x", "y", "z"])
    xyz = np.stack([table.column(c).to_numpy(zero_copy_only=False) for c in ("x", "y", "z")], axis=1).astype(np.float32)
    if len(xyz) % N_LANDMARKS:
        raise ValueError(f"{path}: {len(xyz)} rows is not a multiple of {N_LANDMARKS}")
    return xyz.reshape(-1, N_LANDMARKS, 3)


def _work(path: str) -> np.ndarray:
    return featurize(load_parquet(Path(path))).astype(np.float16)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--signs", type=int, default=0, help="keep only the N most frequent signs (0 = all)")
    ap.add_argument("--limit", type=int, default=0, help="cap on sequences, for quick runs")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)

    with open(args.data / "train.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    counts = Counter(r["sign"] for r in rows)
    keep = {s for s, _ in counts.most_common(args.signs)} if args.signs else set(counts)
    rows = [r for r in rows if r["sign"] in keep]
    if args.limit:
        rows = rows[: args.limit]
    labels = sorted(keep)
    index = {s: i for i, s in enumerate(labels)}

    args.out.mkdir(parents=True, exist_ok=True)
    feats = np.lib.format.open_memmap(args.out / "features.npy", mode="w+", dtype=np.float16, shape=(len(rows), T, FEATURE_DIM))
    ok = np.zeros(len(rows), dtype=bool)
    paths = [str(args.data / r["path"]) for r in rows]
    with ProcessPoolExecutor(args.workers) as pool:
        for i, result in enumerate(pool.map(_work, paths, chunksize=64)):
            feats[i] = result
            ok[i] = True
            if i % 5000 == 0:
                print(f"{i}/{len(rows)}", flush=True)
    feats.flush()
    np.save(args.out / "labels.npy", np.array([index[r["sign"]] for r in rows], dtype=np.int32))
    np.save(args.out / "participants.npy", np.array([int(r["participant_id"]) for r in rows], dtype=np.int32))
    (args.out / "labels.json").write_text(json.dumps(labels))
    print(f"{ok.sum()} sequences, {len(labels)} signs, {len(set(r['participant_id'] for r in rows))} signers -> {args.out}")


if __name__ == "__main__":
    main()
