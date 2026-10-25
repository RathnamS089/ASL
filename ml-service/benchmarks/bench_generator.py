"""Benchmark a gloss-to-text generator on the fixed gloss set.

Measures what the model host (the M4 Mac) actually does; it downloads nothing. Point it at a running
server (vLLM or llama-server) or use the template baseline:

    python benchmarks/bench_generator.py --backend template
    python benchmarks/bench_generator.py --backend openai_compat \
        --base-url http://127.0.0.1:8002/v1 --model <served-model-name> --runs 3

Writes a JSON report (default benchmarks/results/<timestamp>.json, git-ignored) with
latency percentiles, model acceptance rate and every output, so quality can be
reviewed by a person. Record the hardware, runtime and model file in --notes.
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from visualiser_ml.generation.openai_compat import OpenAICompatConfig, OpenAICompatGenerator  # noqa: E402
from visualiser_ml.generation.template import TemplateGenerator  # noqa: E402
from visualiser_ml.schemas import Segment  # noqa: E402

HERE = Path(__file__).resolve().parent


def normalise(text):
    """Lower-case and drop punctuation, so "Hello, friend." == "hello friend"."""
    return " ".join(re.findall(r"[a-z0-9']+", text.lower()))


def percentile(values, p):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1)))]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["template", "openai_compat"], default="template")
    ap.add_argument("--base-url", default="http://127.0.0.1:8002/v1")
    ap.add_argument("--model", default="", help='served model name; use "default_model" for mlx_lm.server with --adapter-path')
    ap.add_argument("--runs", type=int, default=1, help="repeat the whole set this many times")
    ap.add_argument("--thinking", action="store_true", help="leave the model's thinking mode on")
    ap.add_argument("--timeout", type=float, default=60)
    ap.add_argument("--max-tokens", type=int, default=96, help="raise for --thinking runs")
    ap.add_argument("--cases", type=Path, default=HERE / "glosses.jsonl",
                    help="gloss set to score, e.g. finetune/data/test_glosses.jsonl")
    ap.add_argument("--notes", default="", help="hardware, runtime, quantisation, execution provider")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    if args.backend == "template":
        gen = TemplateGenerator()
    else:
        if not args.model:
            ap.error("--model is required for openai_compat")
        gen = OpenAICompatGenerator(OpenAICompatConfig(args.base_url, args.model, timeout_s=args.timeout,
                                                       max_tokens=args.max_tokens,
                                                       disable_thinking=not args.thinking))

    cases = [json.loads(line) for line in args.cases.read_text().splitlines() if line.strip()]
    rows, latencies = [], []
    for run in range(args.runs):
        for case in cases:
            segments = [Segment(g, i, i + 0.5, None) for i, g in enumerate(case["glosses"])]
            started = time.perf_counter()
            result = gen.generate(segments, sign_language="ase")
            ms = (time.perf_counter() - started) * 1000
            latencies.append(ms)
            rows.append({"run": run, "glosses": case["glosses"], "reference": case["reference"],
                         "output": result.text, "source": result.source,
                         "exact_match": normalise(result.text) == normalise(case["reference"]),
                         "rejected_reason": result.rejected_reason, "latency_ms": round(ms, 1)})

    accepted = sum(r["source"] == "model" for r in rows)
    exact = sum(r["exact_match"] for r in rows)
    report = {
        "backend": args.backend, "model": args.model or None, "thinking": args.thinking,
        "max_tokens": args.max_tokens,
        "host": {"machine": platform.machine(), "system": platform.system(),
                 "python": platform.python_version()},
        "notes": args.notes, "case_file": args.cases.name, "cases": len(rows),
        "exact_match_rate": round(exact / len(rows), 3),
        "model_acceptance_rate": round(accepted / len(rows), 3) if args.backend != "template" else None,
        "latency_ms": {"p50": round(statistics.median(latencies), 1),
                       "p95": round(percentile(latencies, 95), 1), "max": round(max(latencies), 1)},
        "rows": rows,
    }
    out = args.out or HERE / "results" / f"{time.strftime('%Y%m%d-%H%M%S')}-{args.backend}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
    print(f"full report: {out}")


if __name__ == "__main__":
    main()
