# Fine-tuning the generator (MLX LoRA on the M4)

This folder teaches Qwen3.5-2B to turn glosses into English using a LoRA adapter. The base model stays unchanged; the adapter is a 22 MB add-on.

| File | What it is |
| --- | --- |
| `pairs.tsv` | Source of truth: one `GLOSSES<TAB>sentence` per line. 304 starter pairs. |
| `build_dataset.py` | Checks every pair, then writes `data/{train,valid,test}.jsonl` (244 / 30 / 30, fixed seed) |
| `lora_config.yaml` | Training settings for 16 GB of memory |
| `data/`, `adapters/` | Generated locally, git-ignored |

**About the starter pairs.** They were written for this project in an ASL-style gloss notation and **have not been reviewed by a fluent signer**. Treat them as a placeholder until someone fluent checks and extends them. Every pair must pass the generation constraint, and none may repeat a row of `benchmarks/glosses.jsonl`. `build_dataset.py` and `tests/test_finetune.py` enforce both. Training examples use exactly the chat the server sends at runtime (`build_messages`), including Qwen's empty thinking block, so training and serving cannot drift apart.

## Run it

All commands run from `ml-service/`. The model must already be in `models/Qwen3.5-2B`; see `MODEL_SELECTION.md`.

1. Build the data:

   ```bash
   .venv/bin/python finetune/build_dataset.py
   ```

2. Train. This took **62 minutes** on the M4 (300 steps); keep the Mac plugged in.

   ```bash
   .venv/bin/mlx_lm.lora -c finetune/lora_config.yaml 2>&1 | tee finetune/adapters/train.log
   ```

3. Serve the model with the adapter:

   ```bash
   .venv/bin/mlx_lm.server --model models/Qwen3.5-2B --adapter-path finetune/adapters/qwen35-2b-gloss --host 127.0.0.1 --port 8002
   ```

4. Evaluate on the benchmark and on the held-out test split:

   ```bash
   .venv/bin/python benchmarks/bench_generator.py --backend openai_compat --model default_model --cases benchmarks/glosses.jsonl --runs 3
   ```

   ```bash
   .venv/bin/python benchmarks/bench_generator.py --backend openai_compat --model default_model --cases finetune/data/test_glosses.jsonl
   ```

**Important:** request `default_model`, not the model path. `mlx_lm.server` attaches the adapter only to `default_model`. A request naming the path silently loads a second copy of the base model **without** the adapter. That happened in our first evaluation and gave outputs identical to the base model. For the service, set `GEN_MODEL=default_model` when the server has an adapter.

## Results (2026-10-25, Apple M4 16 GB, mlx-lm 0.32.2, thinking off)

"Exact" means identical to the reference after lower-casing and dropping punctuation. It is strict: "Tomorrow it will rain." counts as a miss against "It will rain tomorrow." "Pass" means the model's output passed the constraint; otherwise the template was used. Reports are in `benchmarks/reports/`.

| Model | Benchmark (16 rows): exact / pass | Held-out test (30 rows): exact / pass | p50 latency |
| --- | --- | --- | --- |
| Base Qwen3.5-2B | **75% / 100%** | 60% / 80% | ~1.0 s |
| + LoRA, 100 steps | 56% / 69% | 63% / 77% | ~1.1 s |
| + LoRA, 200 steps | 69% / 81% | 70% / 90% | ~1.0 s |
| + LoRA, 300 steps | **75% / 94%** | **80% / 93%** | ~1.1 s |

Final test loss at 300 steps: 0.066 (perplexity 1.068). The per-step training and validation losses were not kept for this run, because the log was filtered. Use the `tee` command above next time.

**What got better**
- Tense comes from time signs: "Last week I traveled.", "Next week I will travel."
- Present tense without a time sign: "Now I am going."
- Name and possessive patterns: "My name is Ana.", "My friend's name is Kai.", "My head hurts."

**What got worse**
- **WH-questions keep sign order.** `YOU NAME WHAT` now gives "Your name is what?" (the base model said "What is your name?"). Similarly "Your birthday is when."
- **It sometimes drops a sign**, for example "I go store tomorrow." without TOMORROW, so the constraint rejects it and the template is used. That is why the pass rate falls on the benchmark.

**Verdict.** Don't switch the service to the adapter yet. It clearly helps on held-out rows written in the same style as the training data. That number is optimistic, because one author wrote both. It does not beat the base model on the independent benchmark. Next round:
1. Add 50 or more WH-final question pairs.
2. Have a fluent signer review `pairs.tsv`.
3. Retrain, and compare again with the same two commands.
