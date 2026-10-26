"""Small MLX transformer that classifies one isolated sign from [T, FEATURE_DIM] features."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import mlx.core as mx
import mlx.nn as nn

from .features import FEATURE_DIM, FEATURE_VERSION, T


@dataclass
class ModelConfig:
    n_classes: int
    in_dim: int = FEATURE_DIM
    frames: int = T
    dim: int = 192
    depth: int = 3
    heads: int = 4
    dropout: float = 0.2
    feature_version: int = FEATURE_VERSION


class SignClassifier(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.cfg = cfg
        self.proj = nn.Sequential(nn.Linear(cfg.in_dim, cfg.dim), nn.GELU(), nn.Linear(cfg.dim, cfg.dim))
        self.pos = mx.zeros((cfg.frames, cfg.dim))
        self.blocks = [nn.TransformerEncoderLayer(cfg.dim, cfg.heads, mlp_dims=cfg.dim * 2, dropout=cfg.dropout, norm_first=True)
                       for _ in range(cfg.depth)]
        self.norm = nn.LayerNorm(cfg.dim)
        self.drop = nn.Dropout(cfg.dropout)
        self.head = nn.Linear(cfg.dim, cfg.n_classes)

    def __call__(self, x: mx.array) -> mx.array:
        h = self.proj(x) + self.pos
        for block in self.blocks:
            h = block(h, None)
        return self.head(self.drop(self.norm(h).mean(axis=1)))


def save(model: SignClassifier, labels: list[str], out_dir: Path, metrics: dict | None = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_weights(str(out_dir / "weights.safetensors"))
    (out_dir / "config.json").write_text(json.dumps(asdict(model.cfg), indent=2))
    (out_dir / "labels.json").write_text(json.dumps(labels, indent=0))
    if metrics is not None:
        (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))


def load(model_dir: Path) -> tuple[SignClassifier, list[str]]:
    cfg = ModelConfig(**json.loads((model_dir / "config.json").read_text()))
    if cfg.feature_version != FEATURE_VERSION or cfg.in_dim != FEATURE_DIM or cfg.frames != T:
        raise ValueError(f"model in {model_dir} was trained on feature version {cfg.feature_version}; "
                         f"this code produces version {FEATURE_VERSION}. Retrain or check out matching code.")
    labels = json.loads((model_dir / "labels.json").read_text())
    if len(labels) != cfg.n_classes:
        raise ValueError("labels.json does not match the model's class count")
    model = SignClassifier(cfg)
    model.load_weights(str(model_dir / "weights.safetensors"))
    model.eval()
    return model, labels
