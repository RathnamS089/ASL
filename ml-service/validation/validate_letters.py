"""Score the A–Z hand-shape classifier on "Learn ASL ABCs with Memory Tips"
(youtube.com/watch?v=wvTrlW5z4SM), a signer the classifier never trained on.

    python validation/validate_letters.py

Reuses the landmark caches from validate_alphabet.py (hand-only fallback, hand in the
right or left slot). Per letter span: frame accuracy, the span's vote (most common
confident frame prediction) and what LetterReader spells. Writes reports/letters.json.
"""
from __future__ import annotations

import json
import string
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from validate_alphabet import MOTION, VIDEO, spans, track  # noqa: E402
from visualiser_ml.recognition.letters import LETTERS, LetterReader, track_hands  # noqa: E402


def main():
    reader = LetterReader(ROOT / "models/letters/asl-mlp")
    report = {}
    for side in ("right", "left"):
        xyz, times = track(side)
        feats, present = track_hands(xyz)
        probs = np.zeros((len(feats), 26), np.float32)
        probs[present] = reader.frame_probabilities(feats[present])
        rows = []
        for letter, start, end in spans():
            i, j = np.searchsorted(times, start), np.searchsorted(times, end)
            m = present[i:j]
            pred = probs[i:j][m].argmax(axis=1)
            conf = probs[i:j][m].max(axis=1)
            frame_acc = float((pred == LETTERS.index(letter.upper())).mean()) if m.any() else 0.0
            confident = [LETTERS[k] for k, c in zip(pred, conf) if c >= reader.min_confidence]
            vote = Counter(confident).most_common(1)[0][0] if confident else ""
            spelled = "".join(l.char for l in reader.read(xyz[i:j], times[i:j]))
            rows.append({"letter": letter.upper(), "frame_accuracy": round(frame_acc, 3), "vote": vote,
                         "correct": vote == letter.upper(), "spelled": spelled})
        static = [r for r in rows if r["letter"].lower() not in MOTION]
        res = {"span_accuracy": round(sum(r["correct"] for r in rows) / 26, 3),
               "static_span_accuracy": round(sum(r["correct"] for r in static) / len(static), 3),
               "mean_frame_accuracy": round(float(np.mean([r["frame_accuracy"] for r in rows])), 3), "rows": rows}
        report[side] = res
        print(f"hand slot={side}: span vote {sum(r['correct'] for r in rows)}/26 ({res['span_accuracy']:.0%}), "
              f"static letters {res['static_span_accuracy']:.0%}, mean frame accuracy {res['mean_frame_accuracy']:.0%}")
        print("   votes:  " + " ".join(r["vote"] or "·" for r in rows))
        print("   truth:  " + " ".join(string.ascii_uppercase))
    best = max(report, key=lambda k: report[k]["span_accuracy"])
    print(f"\nbest slot: {best}")
    for r in report[best]["rows"]:
        print(f"  {r['letter']}: vote={r['vote'] or '-':2} {'ok  ' if r['correct'] else 'MISS'} frames={r['frame_accuracy']:.0%}  spelled={r['spelled']!r}")
    out = Path(__file__).parent / "reports" / "letters.json"
    out.write_text(json.dumps({"video": "youtube.com/watch?v=wvTrlW5z4SM", "model": "asl-letters-mlp", "best_slot": best, **report}, indent=1))
    print("report:", out.relative_to(ROOT))


if __name__ == "__main__":
    main()
