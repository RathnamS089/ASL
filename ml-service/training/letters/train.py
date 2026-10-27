"""Train the A–Z hand-shape classifier (MLX MLP) on prepared landmark features.

    python training/letters/train.py --features data/letters/features.npz --out models/letters/asl-mlp
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import mlx.core as mx  # noqa: E402
import mlx.nn as nn  # noqa: E402
import mlx.optimizers as optim  # noqa: E402

from visualiser_ml.recognition.letters import LETTERS, LetterModelConfig, build_mlp, save  # noqa: E402


def augment(X: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Rotate in the image plane (±15°), rescale (±15%), jitter, and mirror 20% of hands."""
    P = X.reshape(len(X), 21, 3).copy()
    a = rng.uniform(-np.pi / 12, np.pi / 12, len(X))
    c, s = np.cos(a)[:, None], np.sin(a)[:, None]
    x, y = P[..., 0].copy(), P[..., 1].copy()
    P[..., 0], P[..., 1] = c * x - s * y, s * x + c * y
    P *= rng.uniform(0.85, 1.15, (len(X), 1, 1))
    P += rng.normal(0, 0.02, P.shape)
    flip = rng.random(len(X)) < 0.2
    P[flip, :, 0] *= -1
    return P.reshape(len(X), -1).astype(np.float32)


def accuracy(model, X, y):
    model.eval()
    pred = np.array(model(mx.array(X)).argmax(axis=1))
    model.train()
    return float((pred == y).mean())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)

    d = np.load(args.features)
    X, y = d["X"].astype(np.float32), d["y"]
    rng = np.random.default_rng(args.seed)
    idx = rng.permutation(len(y))
    n_val = len(y) * 15 // 100
    va, tr = idx[:n_val], idx[n_val:]
    mx.random.seed(args.seed)
    cfg = LetterModelConfig()
    model = build_mlp(cfg)
    steps = args.epochs * ((len(tr) + 127) // 128)
    opt = optim.AdamW(learning_rate=optim.cosine_decay(2e-3, steps), weight_decay=1e-3)
    step = nn.value_and_grad(model, lambda m, xb, yb: nn.losses.cross_entropy(m(xb), yb, label_smoothing=0.05, reduction="mean"))
    best, started = 0.0, time.time()
    for epoch in range(args.epochs):
        order = rng.permutation(tr)
        for i in range(0, len(order), 128):
            b = order[i:i + 128]
            loss, grads = step(model, mx.array(augment(X[b], rng)), mx.array(y[b]))
            opt.update(model, grads)
            mx.eval(model.parameters(), opt.state)
        acc = accuracy(model, X[va], y[va])
        if acc > best:
            best = acc
            save(model, cfg, args.out)
        if (epoch + 1) % 10 == 0:
            print(f"epoch {epoch + 1}: loss {loss.item():.3f}  val {acc:.3f}", flush=True)
    metrics = {"val_accuracy": round(best, 4), "train": int(len(tr)), "val": int(n_val), "classes": LETTERS,
               "minutes": round((time.time() - started) / 60, 2),
               "note": "val is a random split of the same image collection; see validation/validate_letters.py for a real-video test"}
    (args.out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (args.out / "VERSION").write_text("asl-letters-mlp-v1\n")
    print(json.dumps({k: v for k, v in metrics.items() if k != "classes"}))


if __name__ == "__main__":
    main()
