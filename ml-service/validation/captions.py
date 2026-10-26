"""Word-level timestamps from YouTube auto-caption VTT files (validation only)."""
from __future__ import annotations

import re
from pathlib import Path

_TS = r"(\d+):(\d+):(\d+)\.(\d+)"


def _secs(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def words(vtt: Path) -> list[tuple[float, str]]:
    """[(time, word)] in order, deduplicated across YouTube's rolling cues."""
    text = vtt.read_text(encoding="utf-8")
    out: list[tuple[float, str]] = []
    seen: set[tuple[int, str]] = set()
    for cue in re.finditer(_TS + r" --> " + _TS + r"[^\n]*\n(.*?)(?:\n\n|\Z)", text, re.S):
        start = _secs(*cue.groups()[:4])
        body = cue.group(9)
        if "<c>" not in body:
            continue  # rolling duplicate lines carry no word timing
        first = re.split(r"<\d", body, maxsplit=1)[0]
        pieces = [(start, first)] + [(_secs(*m.groups()[:4]), m.group(5))
                                      for m in re.finditer(_TS + r"><c>(.*?)</c>", body)]
        for t, w in pieces:
            for token in re.findall(r"[A-Za-z']+", w):
                key = (round(t * 10), token.lower())
                if key not in seen:
                    seen.add(key)
                    out.append((t, token.lower()))
    return sorted(out)
