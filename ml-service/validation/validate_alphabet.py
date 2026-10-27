"""Score fingerspelling on "Learn ASL ABCs with Memory Tips" (youtube.com/watch?v=wvTrlW5z4SM).

    python validation/validate_alphabet.py

The video shows one close-up hand (no face or body), so extraction uses the hand-only
fallback. Letter spans come from the video's English captions: each runs from where the
letter is first named to where the next one is. For each span we decode the window and
count it correct when the letter is the most frequent decoded character. Tries both
standardisation modes and both hand slots, and writes validation/reports/alphabet.json.
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

from visualiser_ml.recognition.fingerspelling import FingerspellingReader  # noqa: E402
from visualiser_ml.recognition.landmarks import HolisticExtractor  # noqa: E402

VIDEO = ROOT / "data/youtube/wvTrlW5z4SM.mp4"
# Letter → start second (first time it is named in the captions). S starts after the
# "Now A is like this" comparison so the A shown inside S's span is not counted against it.
STARTS = {"a": 19.7, "b": 25.5, "c": 34.0, "d": 39.5, "e": 48.0, "f": 55.5, "g": 64.6, "h": 75.5, "i": 83.0,
          "j": 89.5, "k": 96.5, "l": 113.0, "m": 118.0, "n": 126.5, "o": 135.0, "p": 140.1, "q": 155.0,
          "r": 167.5, "s": 181.0, "t": 184.0, "u": 193.0, "v": 199.0, "w": 205.0, "x": 211.0, "y": 219.8, "z": 228.0}
END = 233.4
MOTION = {"j", "z"}  # drawn in the air rather than held


def spans():
    keys = list(string.ascii_lowercase)
    for i, k in enumerate(keys):
        yield k, STARTS[k], STARTS[keys[i + 1]] if i + 1 < len(keys) else END


def track(side: str):
    cache = VIDEO.with_name(f"{VIDEO.stem}.hands-{side}.npz")
    if cache.exists():
        d = np.load(cache)
        return d["xyz"], d["times"]
    ex = HolisticExtractor(ROOT / "models/mediapipe/holistic_landmarker.task", target_fps=30, max_seconds=1e9,
                           hand_model_path=ROOT / "models/mediapipe/hand_landmarker.task", hand_fallback_side=side)
    t = ex.extract(VIDEO)
    np.savez_compressed(cache, xyz=t.xyz, times=t.times)
    return t.xyz, t.times


def main():
    reader = FingerspellingReader(ROOT / "models/fingerspelling/openglasses-ctc")
    results = {}
    for side in ("right", "left"):
        xyz, times = track(side)
        seen = np.isfinite(xyz[:, 468:489, 0]).all(1) | np.isfinite(xyz[:, 522:543, 0]).all(1)
        print(f"hand slot={side}: hands found in {seen.mean():.0%} of frames")
        for mode in ("axis", "column", "none"):
            reader.mode = mode
            rows = []
            for letter, start, end in spans():
                i, j = np.searchsorted(times, start), np.searchsorted(times, end)
                decoded = "".join(l.char for l in reader.read(xyz[i:j], times[i:j])).lower()
                letters = [c for c in decoded if c in string.ascii_lowercase]
                guess = Counter(letters).most_common(1)[0][0] if letters else ""
                rows.append({"letter": letter, "decoded": decoded, "guess": guess, "correct": guess == letter})
            static = [r for r in rows if r["letter"] not in MOTION]
            acc = sum(r["correct"] for r in rows) / len(rows)
            acc_static = sum(r["correct"] for r in static) / len(static)
            results[f"{side}/{mode}"] = {"accuracy": round(acc, 3), "static_accuracy": round(acc_static, 3), "rows": rows}
            print(f"  standardise={mode:6}  correct {sum(r['correct'] for r in rows):2}/26 ({acc:.0%})   "
                  f"static letters {acc_static:.0%}   guesses: {''.join(r['guess'] or '·' for r in rows)}")
    best = max(results, key=lambda k: results[k]["accuracy"])
    print(f"\nbest: {best}  ({results[best]['accuracy']:.0%})")
    for r in results[best]["rows"]:
        print(f"  {r['letter'].upper()}: {'ok ' if r['correct'] else 'MISS'} decoded={r['decoded']!r}")
    out = Path(__file__).parent / "reports" / "alphabet.json"
    out.write_text(json.dumps({"video": "youtube.com/watch?v=wvTrlW5z4SM", "best": best, "results": results}, indent=1))
    print("report:", out.relative_to(ROOT))


if __name__ == "__main__":
    main()
