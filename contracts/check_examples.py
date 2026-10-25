#!/usr/bin/env python3
"""Check the shared contract examples against the invariants in docs/API_CONTRACT.md
and docs/ML_CONTRACT.md. Standard library only, so any owner can run it:

    python3 contracts/check_examples.py

Go, web and Python tests should load the same files; this script guards the files themselves.
"""
import json
import sys
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent / "examples"
EMPHASIS = {"normal", "strong", "low_confidence"}
SOURCES = {"model", "template", "mock"}

failures = []


def check(cond, name, msg):
    if not cond:
        failures.append(f"{name}: {msg}")


def load(name):
    with open(EXAMPLES / name, encoding="utf-8") as f:
        return json.load(f)


def check_confidence(name, value, field):
    check(value is None or (isinstance(value, (int, float)) and 0 <= value <= 1),
          name, f"{field} must be null or in [0, 1], got {value!r}")


def check_segments(name, segments, duration=None):
    prev_end = 0.0
    for i, s in enumerate(segments):
        start, end = s["start_seconds"], s["end_seconds"]
        check(s["label"].strip() != "", name, f"segment {i} has an empty label")
        check(0 <= start <= end, name, f"segment {i} needs 0 <= start <= end")
        check(start >= prev_end, name, f"segment {i} overlaps or is out of order")
        if duration is not None:
            check(end <= duration, name, f"segment {i} ends after the clip")
        check_confidence(name, s.get("confidence"), f"segment {i} confidence")
        prev_end = end


def check_tokens(name, tokens, text, index_field, n_segments):
    check(" ".join(t["text"] for t in tokens) == text, name, "tokens do not join to the sentence")
    for i, t in enumerate(tokens):
        idx = t[index_field]
        check(idx is None or 0 <= idx < n_segments, name, f"token {i} {index_field} out of range")
        check(t["emphasis"] in EMPHASIS, name, f"token {i} has unknown emphasis")


def check_error(name, body):
    err = body["error"]
    for key in ("code", "message", "request_id", "retryable"):
        check(key in err, name, f"error.{key} is required")


def check_translation_response(name, r):
    # Required by the existing iOS DTO (VisualiserCore TranslationResponse).
    for key in ("id", "sentence", "signs", "is_mock"):
        check(key in r, name, f"{key} is required")
    check(r["sentence"].strip() != "", name, "sentence must not be empty")
    check_segments(name, r["signs"])
    check_tokens(name, r["tokens"], r["sentence"], "sign_index", len(r["signs"]))
    check(r["generation"]["source"] in SOURCES, name, "unknown generation.source")


def check_ml_response(name, r):
    rec = r["recognition"]
    check_segments(name, rec["segments"], rec["duration_seconds"])
    check_confidence(name, rec["overall_confidence"], "overall_confidence")
    gen = r["generation"]
    if not rec["segments"]:
        check(gen is None, name, "generation must be null when no segments were recognized")
    elif gen is not None:
        check_tokens(name, gen["tokens"], gen["text"], "segment_index", len(rec["segments"]))
        check(gen["source"] in SOURCES, name, "unknown generation.source")


def main():
    check_translation_response("translation-response.json", load("translation-response.json"))
    check_error("error-response.json", load("error-response.json"))
    meta = load("translation-request-metadata.json")
    check(len(json.dumps(meta).encode()) <= 4096, "translation-request-metadata.json", "over 4 KiB")
    req = load("ml-infer-request.json")
    check(req["limits"]["min_seconds"] < req["limits"]["max_seconds"], "ml-infer-request.json", "bad limits")
    for name in ("ml-infer-response.json", "ml-infer-response-no-signs.json"):
        check_ml_response(name, load(name))

    unchecked = {p.name for p in EXAMPLES.glob("*.json")} - {
        "translation-response.json", "error-response.json", "translation-request-metadata.json",
        "ml-infer-request.json", "ml-infer-response.json", "ml-infer-response-no-signs.json",
    }
    check(not unchecked, "examples/", f"add checks for {sorted(unchecked)}")

    if failures:
        print("\n".join(failures))
        return 1
    print("All contract examples satisfy the documented invariants.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
