"""Build MLX LoRA chat data from finetune/pairs.tsv.

    python finetune/build_dataset.py            # writes finetune/data/{train,valid,test}.jsonl

Each example is exactly the chat the generator sends at serving time
(`build_messages`), plus the expected JSON answer, so training and serving prompts
match. Every pair must pass the generation constraint and must not repeat a
benchmark gloss sequence. The split is deterministic (seeded shuffle).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from visualiser_ml.generation.constraints import align  # noqa: E402
from visualiser_ml.generation.openai_compat import build_messages  # noqa: E402
from visualiser_ml.schemas import Segment  # noqa: E402

PAIRS = ROOT / "finetune" / "pairs.tsv"
BENCHMARK = ROOT / "benchmarks" / "glosses.jsonl"
WH = {"WHAT", "WHERE", "WHO", "WHEN", "WHY", "HOW"}


def load_pairs(path: Path = PAIRS) -> list[tuple[list[str], str]]:
    pairs = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        try:
            glosses, sentence = line.split("\t")
        except ValueError:
            raise ValueError(f"{path.name}:{n}: expected 'GLOSSES<TAB>sentence'") from None
        pairs.append((glosses.split(), sentence.strip()))
    return pairs


def problems(pairs: list[tuple[list[str], str]]) -> list[str]:
    bench = {tuple(json.loads(l)["glosses"]) for l in BENCHMARK.read_text().splitlines() if l.strip()}
    seen: set[tuple[str, ...]] = set()
    found = []
    for glosses, sentence in pairs:
        key = tuple(glosses)
        if key in bench:
            found.append(f"{' '.join(glosses)}: repeats a benchmark row")
        if key in seen:
            found.append(f"{' '.join(glosses)}: duplicate")
        seen.add(key)
        _, reason = align(sentence, [Segment(g, i, i + 0.5) for i, g in enumerate(glosses)], None)
        if reason:
            found.append(f"{' '.join(glosses)} -> {sentence}: {reason}")
    return found


def example(glosses: list[str], sentence: str) -> dict:
    # Emphasise the WH-sign in questions, like the few-shot examples; nothing otherwise.
    emphasize = [i for i, g in enumerate(glosses) if g in WH] if sentence.endswith("?") else []
    answer = json.dumps({"sentence": sentence, "emphasize": emphasize})
    return {"messages": build_messages(glosses) + [{"role": "assistant", "content": answer}]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "finetune" / "data")
    ap.add_argument("--valid", type=float, default=0.1)
    ap.add_argument("--test", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)

    pairs = load_pairs()
    if found := problems(pairs):
        print("\n".join(found))
        return 1
    random.Random(args.seed).shuffle(pairs)
    n_test, n_valid = round(len(pairs) * args.test), round(len(pairs) * args.valid)
    splits = {"test": pairs[:n_test], "valid": pairs[n_test:n_test + n_valid], "train": pairs[n_test + n_valid:]}
    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows in splits.items():
        with open(args.out / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for glosses, sentence in rows:
                f.write(json.dumps(example(glosses, sentence)) + "\n")
        # Same rows in benchmark format, so bench_generator.py can score them.
        with open(args.out / f"{name}_glosses.jsonl", "w", encoding="utf-8") as f:
            for glosses, sentence in rows:
                f.write(json.dumps({"glosses": glosses, "reference": sentence}) + "\n")
    print(", ".join(f"{k}: {len(v)}" for k, v in splits.items()), f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
