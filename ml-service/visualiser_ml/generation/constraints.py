"""The generation constraint from docs/ML_CONTRACT.md, invariant 6:
every content word must come from a recognized gloss; only function words,
punctuation and inflection may be added.

The rules are deliberately simple and conservative. A false rejection only costs
a fallback to the template; a false acceptance shows the user words nobody signed.
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from ..schemas import Emphasis, Segment, Token

# Words a generator may add without a gloss. Keep this list small and reviewed:
# anything here can appear in output without having been signed.
FUNCTION_WORDS = frozenset("""
a an the and or but so to of in on at for with from by as
is are am was were be been being do does did have has had will would can could
i me my you your he him his she her it its we us our they them their
this that these those there here not no
""".split())

# Common ASL-style gloss conventions mapped to English surface words.
GLOSS_ALIASES = {
    "IX-1": ("i", "me", "my"),
    "ME": ("i", "me"),
    "IX-2": ("you", "your"),
    "YOU": ("you", "your"),
    "IX-3": ("he", "she", "it", "they", "him", "her", "them"),
    "MY": ("my", "mine"),
    "POSS-1": ("my", "mine"),
}

IRREGULAR = {
    "go": ("went", "gone"), "eat": ("ate", "eaten"), "see": ("saw", "seen"),
    "come": ("came",), "have": ("had", "has"), "be": ("is", "are", "was", "were", "am"),
    "give": ("gave", "given"), "know": ("knew", "known"), "take": ("took", "taken"),
    "child": ("children",), "person": ("people",), "man": ("men",), "woman": ("women",),
}

SUFFIXES = ("", "s", "es", "ed", "d", "ing", "er", "ers", "ly", "'s")

_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


def words(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text)]


def gloss_surface_forms(label: str) -> set[str]:
    """All lower-case English words a single gloss may legitimately produce."""
    label = label.strip().upper()
    if label in GLOSS_ALIASES:
        return set(GLOSS_ALIASES[label])
    if label.startswith("FS-"):  # fingerspelling, e.g. FS-JOHN
        return {label[3:].lower()}
    forms: set[str] = set()
    for part in re.split(r"[-+_\s]+", label):
        base = part.lower()
        if not base.isalpha():
            continue
        forms.update(base + s for s in SUFFIXES)
        if base.endswith("e"):
            forms.update(base[:-1] + s for s in ("ing", "ed", "er"))
        forms.update(IRREGULAR.get(base, ()))
    return forms


def align(text: str, segments: Sequence[Segment], low_confidence_threshold: float | None,
          emphasize: Sequence[int] = ()) -> tuple[list[Token], str | None]:
    """Split `text` on spaces into tokens and map each to the segment it came from.

    Returns (tokens, rejection_reason). The reason is None when the text satisfies
    the constraint: every non-function word maps to a segment and every segment is
    expressed at least once. Word order may differ from signing order, because
    English and sign-language grammar differ (ASL often puts WH-signs last).
    """
    forms = [gloss_surface_forms(s.label) for s in segments]
    tokens: list[Token] = []
    used: set[int] = set()
    for raw in text.split():
        index: int | None = None
        for w in words(raw):
            candidates = [i for i in range(len(segments)) if w in forms[i]]
            if not candidates:
                if w in FUNCTION_WORDS:
                    continue
                return [], f"word {w!r} does not come from any recognized sign"
            # Prefer the first sign not yet expressed; otherwise the word repeats one.
            index = next((i for i in candidates if i not in used), candidates[0])
            used.add(index)
        tokens.append(Token(raw, index, _emphasis(index, segments, low_confidence_threshold, emphasize)))
    missing = [segments[i].label for i in range(len(segments)) if i not in used]
    if missing:
        return [], f"signs not expressed in the text: {', '.join(missing)}"
    if not tokens:
        return [], "empty text"
    return tokens, None


def _emphasis(index: int | None, segments: Sequence[Segment], threshold: float | None,
              emphasize: Sequence[int]) -> Emphasis:
    if index is None:
        return "normal"
    conf = segments[index].confidence
    if threshold is not None and conf is not None and conf < threshold:
        return "low_confidence"
    return "strong" if index in emphasize else "normal"
