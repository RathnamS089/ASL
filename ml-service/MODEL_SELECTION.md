# Generator model selection: vLLM and small reasoning models

Owner: Language/inference. Status: **Qwen3.5-2B downloaded and benchmarked on the Apple M4 Mac that hosts the models (2026-10-25).** Numbers in the candidate table come from the cited sources. Numbers in "Our measurements" come from `benchmarks/bench_generator.py`, with the raw reports in `benchmarks/reports/`.

## Our measurements

Setup:
- **Machine:** Apple M4, 16 GB RAM, macOS
- **Server:** `mlx_lm.server` (mlx-lm 0.32.2) on Metal
- **Model:** the official `Qwen/Qwen3.5-2B` weights in bf16 (4.55 GB on disk)
- **Test set:** the 16-row gloss set; thinking-off runs repeat it 3 times (48 requests)
- **Constraint:** v2 (negation must be signed; contractions allowed)

| Generator | Acceptance (passed the constraint) | p50 latency | p95 latency | Report |
| --- | --- | --- | --- | --- |
| Template (baseline) | — (always passes) | < 1 ms | < 1 ms | `m4-template.json` |
| **Qwen3.5-2B, thinking off** | **100% (48/48)** | **976 ms** | **1,118 ms** | `m4-qwen35-2b-nothink.json` |
| Qwen3.5-2B, thinking on (max 1,024 tokens) | 0% (0/16): never produced the JSON answer | 46.3 s | 47.1 s | `m4-qwen35-2b-think.json` |

What the outputs show (human reading of the thinking-off report, not a formal score):
- **Exact matches.** 12 of the 16 rows match the reference exactly, for example `YOU NAME WHAT` → "What is your name?" and `YESTERDAY IX-1 EAT PIZZA` → "Yesterday I ate pizza."
- **Fluent but different meaning.** `IX-1 NAME FS-ANA` → "I will name Ana." (the reference is "My name is Ana"). The constraint cannot catch this, because no word was invented.
- **Guessed tense.** `IX-1 LEARN SIGN LANGUAGE` → "I will learn sign language." Glosses carry no tense, so the model guesses one.
- **Small additions.** `MOTHER WORK HOSPITAL` → "My mother works in the hospital." The added "my" is allowed as a function word.
- **Thinking mode.** The steady ~46 s per request suggests the model used the whole 1,024-token budget reasoning and never reached an answer. Either way, it is unusable for this task at this latency.

Decision input for D9:
- **Use the model.** With thinking off, Qwen3.5-2B is clearly more fluent than the template ("Where is the bathroom?" vs "Where bathroom.") at about 1 s on the M4.
- **Benchmark one more candidate** (SmolLM3-3B, then Qwen3.5-4B) on the same M4 setup before deciding.
- **Fine-tuning, if done**, should target meaning errors like the "name" row. A small team-written corpus and an MLX LoRA run are enough to try that; see [`docs/DATASETS.md`](../docs/DATASETS.md).
- **Template bug found.** The template produces "Please help I." for `PLEASE HELP IX-1`, because it always renders IX-1 as "I". This is a known weakness of the fallback.

## What the generator does

It turns a short gloss sequence from the recognizer, typically one to eight glosses such as `IX-1 GO STORE TOMORROW`, into one English sentence ("I will go to the store tomorrow."). The task is short, needs only a little grammar knowledge, and must not hallucinate. So the requirements are, in order:

1. **Faithfulness.** Enforced in code by `generation/constraints.py`. When the model invents a content word or drops a sign, the template fallback takes over.
2. **Latency on the M4.** It should add about a second or less per request. Measured: 976 ms p50 for Qwen3.5-2B.
3. **Memory.** The model must fit next to the recognizer, the Go API and a browser in the Mac's 16 GB of unified memory. Qwen3.5-2B in bf16 is 4.55 GB.
4. **Licence.** Permissive (Apache-2.0 or MIT) so the project can be shown or shared without legal review.

Step-by-step "reasoning" (thinking) mode works **against** goal 2 and adds nothing for goal 1, which code enforces. The measurements above confirm it. The adapter therefore turns thinking off by default (`GEN_DISABLE_THINKING=1` sends `chat_template_kwargs: {enable_thinking: false}`) and strips any `<think>…</think>` block it receives.

## Serving on the M4: MLX, llama.cpp or vLLM

The adapter (`generation/openai_compat.py`) talks to the OpenAI-compatible `POST /v1/chat/completions` endpoint, so any of these servers works without code changes. Bind the server to `127.0.0.1:8002` and never expose it to the LAN.

| | **MLX `mlx_lm.server`** (recommended) | llama.cpp `llama-server` | vLLM |
| --- | --- | --- | --- |
| On Apple Silicon | Native, runs on the Metal GPU. **Measured by us.** | Native with the Metal backend (`brew install llama.cpp`). Not measured yet. | CPU only on macOS, built from source ([CPU install docs](https://docs.vllm.ai/en/v0.11.2/getting_started/installation/cpu/)). No Metal, so it is a poor fit for the M4. |
| Model format | Hugging Face safetensors (the official weights) | GGUF (quantised: Q4_K_M, Q8_0, …) | Hugging Face safetensors |
| Structured output | Ignores `response_format`; the adapter validates | JSON schema / grammar sampling | `response_format` with `json_schema` |
| Fine-tuning | **LoRA built in** (`mlx_lm.lora`), on the same files | No | No (serving only) |

**Recommendation.** Use MLX for the MVP. It runs the official weights on the GPU, it is already measured, and the same install does LoRA fine-tuning. Keep llama.cpp as a fallback if a 4-bit GGUF is needed to save memory. vLLM only makes sense later, on a Linux machine with a GPU.

## Running the model on a Mac (Apple Silicon)

```bash
.venv/bin/pip install mlx-lm==0.32.2
```

```bash
.venv/bin/hf download Qwen/Qwen3.5-2B --local-dir models/Qwen3.5-2B
```

```bash
.venv/bin/mlx_lm.server --model models/Qwen3.5-2B --host 127.0.0.1 --port 8002
```

```bash
.venv/bin/python benchmarks/bench_generator.py --backend openai_compat --base-url http://127.0.0.1:8002/v1 --model "$PWD/models/Qwen3.5-2B" --runs 3
```

`mlx_lm.server` honours `chat_template_kwargs` (thinking off), but it ignores `response_format`, so JSON output is not enforced by the server. The adapter parses and validates the output either way. For the service itself, set `GEN_BACKEND=openai_compat`, `GEN_BASE_URL=http://127.0.0.1:8002/v1` and `GEN_MODEL=<absolute model path>`.

## Candidate small models (≤ 4B)

These are small open-weight models with a reasoning or "thinking" mode, chosen from public model cards and roundups ([tinyweights.dev](https://tinyweights.dev/posts/best-small-language-models-2026/), [premai.io](https://blog.premai.io/best-lightweight-language-models-worth-running), [Qwen3.5 Small release coverage](https://gigazine.net/gsc_news/en/20260303-qwen-3-5-small)). **Check each model card and licence before downloading.** Secondary sources sometimes disagree, for example on Qwen3.5-4B's default thinking mode.

| Candidate | Size | Licence (per sources) | Why consider it | Watch out for |
| --- | --- | --- | --- | --- |
| Qwen3.5-2B | 2B | Apache-2.0 | **Measured: 100% acceptance, ~1 s on the M4 with thinking off.** | Weaker than the 4B models. One meaning error in 16 rows. |
| Qwen3.5-4B | 4B | Apache-2.0 | The strongest reported benchmarks in this size class | It may reason by default (sources disagree), and it is twice the memory and latency of the 2B. |
| SmolLM3-3B | 3B | Apache-2.0 | Fully open (data and training recipe), with a dual reasoning mode | Check mlx-lm support and its chat-template thinking switch |
| Phi-4-mini-reasoning | 3.8B | MIT | Built for step-by-step reasoning | Tuned for maths and STEM chain-of-thought, a poor match for short faithful rewriting. It is expected to be slow because it always reasons. |
| Ministral 3 3B | ~3–4B | Apache-2.0 (per roundup) | Strong reasoning for its size | Licence and size need checking on the official card |
| Qwen3.5-0.8B | 0.8B | Apache-2.0 | Fastest option; good for a latency floor | A roundup notes heavy token use in reasoning mode. Quality may be too low. |

**Suggested benchmark order:** template baseline ✓ → Qwen3.5-2B (thinking off) ✓ → SmolLM3-3B (thinking off) → Qwen3.5-4B (thinking off) → the best of these with `--thinking`. Use the official weights with MLX first. If memory gets tight, try an MLX 4-bit conversion (`mlx_lm.convert -q`) and record it in `--notes`.

## Benchmark procedure (milestone 6)

```bash
python benchmarks/bench_generator.py --backend template --notes "baseline"
```

```bash
python benchmarks/bench_generator.py --backend openai_compat --base-url http://127.0.0.1:8002/v1 --model "$PWD/models/<model>" --runs 3 --notes "Apple M4 16 GB, mlx-lm <version>, <model> bf16, Metal"
```

Report for each model:
- `model_acceptance_rate`: how often the output passed the constraint
- p50/p95 latency
- peak memory, from Activity Monitor (Memory column for the server process)
- model load time
- a human 1–5 fluency score on the 16 rows

A model is worth shipping only if it beats the template on fluency **and** keeps a high acceptance rate within the latency budget. Otherwise ship the template, which is honest even though it isn't fluent.

## Should we fine-tune the generator?

**Not before the benchmark says so.** Few-shot prompting plus the constraint may be enough for the vocabulary size the recognizer can actually handle at first (tens to a few hundred glosses). If fine-tuning is needed, see [`docs/DATASETS.md`](../docs/DATASETS.md#gloss--text-for-the-generator). The main ASL gloss→English corpus (ASLG-PC12) is rule-generated and its licence is unclear. A small corpus written by the team for the chosen vocabulary, with LoRA on the chosen 2–4B model, is the more realistic plan.

## GPU and Neural Engine

MLX runs the generator on the M4's GPU through Metal; that is what the measured numbers use. The Neural Engine is not used: neither MLX nor llama.cpp targets it. The ml-service process itself runs on the CPU, which is why `/health` reports `execution_provider: "cpu"`. The generator's device is whatever its separate server uses.
