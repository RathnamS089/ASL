"""Deterministic gloss-to-text fallback. Always available, needs no model.

It only rewrites glosses into readable words; it never adds words, so its output
always passes the constraint. It does not produce fluent English ("Hello my friend.").
"""
from __future__ import annotations

from collections.abc import Sequence

from ..schemas import GenerationResult, Segment
from .constraints import GLOSS_ALIASES, align


def gloss_to_word(label: str) -> str:
    label = label.strip().upper()
    if label in GLOSS_ALIASES:
        return GLOSS_ALIASES[label][0]
    if label.startswith("FS-"):
        return label[3:].capitalize()
    return " ".join(p for p in label.replace("+", "-").replace("_", "-").lower().split("-") if p)


def template_sentence(segments: Sequence[Segment]) -> str:
    words = [gloss_to_word(s.label) for s in segments]
    words = [w for w in words if w]
    if not words:
        return ""
    words = ["I" if w == "i" else w for w in words]
    text = " ".join(words)
    return text[0].upper() + text[1:] + "."


class TemplateGenerator:
    name = "template"
    version = "0.1.0"

    def __init__(self, low_confidence_threshold: float | None = None):
        self.low_confidence_threshold = low_confidence_threshold

    def generate(self, segments: Sequence[Segment], *, sign_language: str,
                 target_language: str = "en", rejected_reason: str | None = None) -> GenerationResult:
        text = template_sentence(segments)
        tokens, reason = align(text, segments, self.low_confidence_threshold)
        if reason:  # would mean a bug in gloss_to_word; fail loudly in tests
            raise ValueError(f"template output violates the constraint: {reason}")
        return GenerationResult(text=text, tokens=tokens, source="template", constrained=True,
                                rejected_reason=rejected_reason)
