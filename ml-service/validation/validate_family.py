"""Score the sign recognizer on the Miacademy ASL family lesson.

    python validation/validate_family.py            # needs data/youtube/N45u5W3rOBc.landmarks.npz

Runs exactly the serving path (segmenter → pretrained ISLR classifier with the same
padding) on each labelled span and review sequence, then writes
validation/reports/family-islr.json and prints a summary.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from family_spans import SEQUENCES, SPANS  # noqa: E402
from visualiser_ml.recognition.islr import IslrRecognizer, load_classifier  # noqa: E402
from visualiser_ml.recognition.segmenter import segment  # noqa: E402

PAD = IslrRecognizer.PAD_FRAMES


def window(xyz, times, start, end):
    i, j = np.searchsorted(times, start), np.searchsorted(times, end)
    return xyz[i:j], times[i:j]


def classify(clf, xyz, times):
    spans = segment(xyz, times, max_signs=50)
    if not spans:
        return []
    n = len(times)
    probs = clf.probabilities([xyz[max(0, s - PAD):min(n, e + PAD)] for s, e in spans])
    out = []
    for (s, e), p in zip(spans, probs):
        top = np.argsort(p)[::-1][:5]
        out.append({"start": round(float(times[s]), 2), "end": round(float(times[e - 1]), 2),
                    "top5": [(clf.labels[int(k)], round(float(p[k]), 3)) for k in top], "probs": p})
    return out


def main():
    data = np.load(ROOT / "data/youtube/N45u5W3rOBc.landmarks.npz")
    xyz, times = data["xyz"], data["times"]
    clf = load_classifier(ROOT / "models/recognizer/islr-1st-place")
    report = {"video": "youtube.com/watch?v=N45u5W3rOBc", "model": "islr-1st-place", "spans": [], "sequences": []}

    print(f"{'sign':12} {'label':8} {'segs':>4} {'top1':>6} {'top5':>6}  {'vote':10} most common top-1 guesses")
    for sign, start, end, label in SPANS:
        segs = classify(clf, *window(xyz, times, start, end))
        tops = [s["top5"][0][0] for s in segs]
        vote = clf.labels[int(np.argmax(np.sum([s["probs"] for s in segs], axis=0)))] if segs else None
        top1 = sum(t == label for t in tops) / len(segs) if segs and label else None
        top5 = sum(any(l == label for l, _ in s["top5"]) for s in segs) / len(segs) if segs and label else None
        common = Counter(tops).most_common(3)
        print(f"{sign:12} {str(label):8} {len(segs):4} {'' if top1 is None else f'{top1:6.0%}'}{'' if top5 is None else f' {top5:6.0%}':>7}  {str(vote):10} {common}")
        report["spans"].append({"sign": sign, "islr_label": label, "start": start, "end": end, "segments": len(segs),
                                "top1_rate": top1, "top5_rate": top5, "span_vote": vote, "vote_correct": vote == label if label else None,
                                "mean_top1_confidence": round(float(np.mean([s["top5"][0][1] for s in segs])), 3) if segs else None,
                                "guesses": [{k: v for k, v in s.items() if k != "probs"} for s in segs]})

    print()
    for name, start, end, expected in SEQUENCES:
        segs = classify(clf, *window(xyz, times, start, end))
        got = [s["top5"][0][0] for s in segs]
        wanted = [l for s, *_, l in SPANS for e in expected if s == e and l]
        print(f"{name}: expected (in vocabulary) {wanted}")
        print(f"{'':10}predicted {got}")
        report["sequences"].append({"name": name, "expected_in_vocab": wanted, "predicted": got,
                                    "confidences": [s["top5"][0][1] for s in segs]})

    inv = [s for s in report["spans"] if s["islr_label"]]
    oov = [s for s in report["spans"] if not s["islr_label"]]
    summary = {
        "in_vocab_signs": len(inv),
        "segment_top1": round(float(np.mean([s["top1_rate"] for s in inv])), 3),
        "segment_top5": round(float(np.mean([s["top5_rate"] for s in inv])), 3),
        "span_vote_correct": sum(bool(s["vote_correct"]) for s in inv),
        "in_vocab_mean_conf": round(float(np.mean([s["mean_top1_confidence"] for s in inv])), 3),
        "out_of_vocab_mean_conf": round(float(np.mean([s["mean_top1_confidence"] for s in oov if s["mean_top1_confidence"] is not None])), 3),
    }
    report["summary"] = summary
    print("\nsummary:", json.dumps(summary))
    out = Path(__file__).parent / "reports" / "family-islr.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=1))
    print("report:", out.relative_to(ROOT))


if __name__ == "__main__":
    main()
