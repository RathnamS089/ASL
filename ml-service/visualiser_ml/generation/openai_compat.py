"""Generator backed by any OpenAI-compatible chat server.

Servers that expose POST {base}/chat/completions:
- MLX `mlx_lm.server`: the default on the Apple Silicon (M4) model host; runs on Metal.
- llama.cpp `llama-server`: also native on Apple Silicon (Metal), for GGUF files.
- vLLM (`vllm serve <model>`): for a Linux GPU machine later; CPU-only on macOS.

The model is asked for JSON `{"sentence": ..., "emphasize": [...]}`. Its output is
never trusted: it is parsed, checked against the gloss constraint, and replaced by
the template on any failure. Uses only the standard library so it adds no
platform-specific dependency.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass

from ..schemas import GenerationResult, Segment
from .constraints import align
from .template import TemplateGenerator

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "sentence": {"type": "string", "minLength": 1, "maxLength": 300},
        "emphasize": {"type": "array", "items": {"type": "integer", "minimum": 0}, "maxItems": 8},
    },
    "required": ["sentence"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You turn sign-language glosses into one short, natural English sentence.
Rules:
- Use every gloss, in the given order, and add no new meaning.
- You may only add these kinds of words: articles, pronouns, auxiliaries, prepositions, conjunctions, and inflections of the glossed words.
- Never add names, places, numbers, adjectives, or other content words that are not glossed.
- Output JSON only: {"sentence": "...", "emphasize": [indices of glosses that deserve visual emphasis]}"""

FEW_SHOT = [
    (["HELLO", "MY", "FRIEND"], {"sentence": "Hello, my friend.", "emphasize": [0]}),
    (["IX-1", "GO", "STORE", "TOMORROW"], {"sentence": "I will go to the store tomorrow.", "emphasize": []}),
    (["YOU", "NAME", "WHAT"], {"sentence": "What is your name?", "emphasize": [2]}),
]

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


@dataclass
class OpenAICompatConfig:
    base_url: str
    model: str
    api_key: str = ""
    timeout_s: float = 20.0
    max_tokens: int = 96
    disable_thinking: bool = True


class GenerationBackendError(Exception):
    pass


class OpenAICompatGenerator:
    name = "openai_compat"
    version = "0.1.0"

    def __init__(self, config: OpenAICompatConfig, low_confidence_threshold: float | None = None):
        self.config = config
        self.low_confidence_threshold = low_confidence_threshold
        self.fallback = TemplateGenerator(low_confidence_threshold)
        self.last_latency_ms: int | None = None

    def generate(self, segments: Sequence[Segment], *, sign_language: str,
                 target_language: str = "en") -> GenerationResult:
        glosses = [s.label for s in segments]
        try:
            content = self._complete(glosses)
            sentence, emphasize = parse_model_output(content, len(segments))
        except GenerationBackendError as e:
            return self.fallback.generate(segments, sign_language=sign_language,
                                          rejected_reason=f"backend: {e}")
        tokens, reason = align(sentence, segments, self.low_confidence_threshold, emphasize)
        if reason:
            return self.fallback.generate(segments, sign_language=sign_language,
                                          rejected_reason=f"constraint: {reason}")
        return GenerationResult(text=" ".join(t.text for t in tokens), tokens=tokens,
                                source="model", constrained=True)

    def _complete(self, glosses: list[str]) -> str:
        messages = build_messages(glosses)
        body = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": self.config.max_tokens,
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "translation", "schema": RESPONSE_SCHEMA, "strict": True}},
        }
        if self.config.disable_thinking:
            # Honoured by vLLM and llama-server for chat templates with a thinking switch
            # (e.g. Qwen3.x); ignored by templates without one.
            body["chat_template_kwargs"] = {"enable_thinking": False}
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        req = urllib.request.Request(self.config.base_url.rstrip("/") + "/chat/completions",
                                     data=json.dumps(body).encode(), headers=headers, method="POST")
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_s) as resp:
                payload = json.load(resp)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            raise GenerationBackendError(type(e).__name__) from e
        finally:
            self.last_latency_ms = round((time.perf_counter() - started) * 1000)
        try:
            return payload["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise GenerationBackendError("malformed completion") from e


def build_messages(glosses: Sequence[str]) -> list[dict]:
    """The exact chat sent to the model. Fine-tuning data is built with this too, so
    training and serving prompts cannot drift apart."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for shot_glosses, answer in FEW_SHOT:
        messages.append({"role": "user", "content": " ".join(shot_glosses)})
        messages.append({"role": "assistant", "content": json.dumps(answer)})
    messages.append({"role": "user", "content": " ".join(glosses)})
    return messages


def parse_model_output(content: str, n_segments: int) -> tuple[str, list[int]]:
    """Extract the sentence from model output, tolerating reasoning blocks."""
    content = _THINK.sub("", content).strip()
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end < start:
        raise GenerationBackendError("no JSON object in output")
    try:
        data = json.loads(content[start:end + 1])
    except json.JSONDecodeError as e:
        raise GenerationBackendError("invalid JSON") from e
    sentence = data.get("sentence") if isinstance(data, dict) else None
    if not isinstance(sentence, str) or not sentence.strip() or len(sentence) > 300:
        raise GenerationBackendError("missing or invalid sentence")
    emphasize = [i for i in data.get("emphasize") or [] if isinstance(i, int) and 0 <= i < n_segments]
    return " ".join(sentence.split()), emphasize
