"""Compare benchmark reports side by side, overall and on WH-question rows.

    python finetune/compare_reports.py base=benchmarks/reports/a.json r2=benchmarks/reports/b.json [--exclude rows.jsonl]

--exclude drops rows whose glosses appear in the given gloss file (for example an
older adapter's training rows), so a model is never scored on data it trained on.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

WH = {"WHAT", "WHERE", "WHO", "WHEN", "WHY", "HOW", "WHICH", "HOW-MUCH"}


def score(rows):
    n = len(rows)
    if not n:
        return "—"
    exact = sum(r["exact_match"] for r in rows)
    passed = sum(r["source"] == "model" for r in rows)
    return f"{exact}/{n} exact ({exact / n:.0%}), {passed}/{n} pass ({passed / n:.0%})"


def main(argv):
    exclude: set[tuple[str, ...]] = set()
    named = []
    args = iter(argv)
    for arg in args:
        if arg == "--exclude":
            path = Path(next(args))
            exclude |= {tuple(json.loads(l)["glosses"]) for l in path.read_text().splitlines() if l.strip()}
        else:
            name, _, path = arg.partition("=")
            named.append((name, json.loads(Path(path).read_text())))
    for name, report in named:
        rows = [r for r in report["rows"] if r["run"] == 0 and tuple(r["glosses"]) not in exclude]
        wh = [r for r in rows if any(g in WH for g in r["glosses"])]
        print(f"{name:10} all: {score(rows):40} WH rows: {score(wh)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
