"""Train the sign classifier with MLX on prepared ISLR features.

    python training/islr/train.py --features data/islr-features --out models/recognizer/islr --epochs 40

Signers are split, not sequences: validation and test signers never appear in training,
so the reported accuracy is for people the model has not seen.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import mlx.core as mx  # noqa: E402
import mlx.nn as nn  # noqa: E402
import mlx.optimizers as optim  # noqa: E402

from visualiser_ml.recognition.model import ModelConfig, SignClassifier, save  # noqa: E402


def split_by_signer(participants: np.ndarray, val: int, test: int, seed: int):
    signers = np.unique(participants)
    rng = np.random.default_rng(seed)
    rng.shuffle(signers)
    test_s, val_s = set(signers[:test]), set(signers[test:test + val])
    is_test = np.isin(participants, list(test_s))
    is_val = np.isin(participants, list(val_s))
    return np.where(~is_test & ~is_val)[0], np.where(is_val)[0], np.where(is_test)[0], sorted(map(int, test_s)), sorted(map(int, val_s))


def augment(x: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Small jitter and frame dropout; geometry is already normalised."""
    x = x + rng.normal(0, 0.01, x.shape).astype(np.float32) * (x != 0)
    drop = rng.random((x.shape[0], x.shape[1], 1)) < 0.1
    return np.where(drop, 0, x).astype(np.float32)


def evaluate(model, X, y, batch=512):
    model.eval()
    top1 = top5 = 0
    for i in range(0, len(y), batch):
        logits = model(mx.array(X[i:i + batch].astype(np.float32)))
        order = np.argsort(-np.array(logits), axis=1)[:, :5]
        t = y[i:i + batch]
        top1 += int((order[:, 0] == t).sum())
        top5 += int((order == t[:, None]).any(axis=1).sum())
    model.train()
    n = max(len(y), 1)
    return top1 / n, top5 / n


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--val-signers", type=int, default=2)
    ap.add_argument("--test-signers", type=int, default=3)
    ap.add_argument("--dim", type=int, default=192)
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)

    X = np.load(args.features / "features.npy", mmap_mode="r")
    y = np.load(args.features / "labels.npy")
    participants = np.load(args.features / "participants.npy")
    labels = json.loads((args.features / "labels.json").read_text())
    tr, va, te, test_signers, val_signers = split_by_signer(participants, args.val_signers, args.test_signers, args.seed)
    print(f"train {len(tr)}  val {len(va)} (signers {val_signers})  test {len(te)} (signers {test_signers})  classes {len(labels)}")
    Xva, Xte = np.asarray(X[va]), np.asarray(X[te])

    mx.random.seed(args.seed)
    rng = np.random.default_rng(args.seed)
    model = SignClassifier(ModelConfig(n_classes=len(labels), dim=args.dim, depth=args.depth))
    steps_per_epoch = math.ceil(len(tr) / args.batch)
    total = steps_per_epoch * args.epochs
    schedule = optim.join_schedules([optim.linear_schedule(1e-5, args.lr, min(500, total // 10)),
                                     optim.cosine_decay(args.lr, total)], [min(500, total // 10)])
    opt = optim.AdamW(learning_rate=schedule, weight_decay=0.05)

    def loss_fn(m, xb, yb):
        return nn.losses.cross_entropy(m(xb), yb, label_smoothing=0.1, reduction="mean")

    step = nn.value_and_grad(model, loss_fn)
    best, history, started = -1.0, [], time.time()
    for epoch in range(args.epochs):
        order = rng.permutation(tr)
        losses = []
        for i in range(0, len(order), args.batch):
            idx = np.sort(order[i:i + args.batch])
            xb = mx.array(augment(np.asarray(X[idx], dtype=np.float32), rng))
            loss, grads = step(model, xb, mx.array(y[idx]))
            opt.update(model, grads)
            mx.eval(model.parameters(), opt.state, loss)
            losses.append(loss.item())
        v1, v5 = evaluate(model, Xva, y[va])
        history.append({"epoch": epoch + 1, "loss": round(float(np.mean(losses)), 4), "val_top1": round(v1, 4), "val_top5": round(v5, 4)})
        print(json.dumps(history[-1]), flush=True)
        if v1 > best:
            best = v1
            save(model, labels, args.out)
    # Final numbers come from the best checkpoint on the held-out test signers.
    from visualiser_ml.recognition.model import load
    best_model, _ = load(args.out)
    t1, t5 = evaluate(best_model, Xte, y[te])
    metrics = {"test_top1": round(t1, 4), "test_top5": round(t5, 4), "best_val_top1": round(best, 4),
               "classes": len(labels), "train": int(len(tr)), "val": int(len(va)), "test": int(len(te)),
               "test_signers": test_signers, "val_signers": val_signers, "epochs": args.epochs,
               "minutes": round((time.time() - started) / 60, 1), "history": history}
    save(best_model, labels, args.out, metrics)
    (args.out / "VERSION").write_text(f"islr-{len(labels)}-v1\n")
    print(json.dumps({k: v for k, v in metrics.items() if k != "history"}, indent=2))


if __name__ == "__main__":
    main()
