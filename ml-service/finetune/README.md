# Fine-tuning the generator (MLX LoRA on the M4)

This folder teaches Qwen3.5-2B to turn glosses into English using a LoRA adapter. The base model stays unchanged; the adapter is a 22 MB add-on.

| File | What it is |
| --- | --- |
| `pairs.tsv` | Source of truth: one `GLOSSES<TAB>sentence` per line. 364 pairs: 304 starter pairs plus 60 WH-questions (round 2). |
| `build_dataset.py` | Checks every pair, then writes `data/{train,valid,test}.jsonl` (306 / 31 / 27). A hash of each pair's glosses picks its split, so adding pairs never moves existing ones. |
| `compare_reports.py` | Side-by-side scores, overall and on WH-question rows, optionally excluding rows a model trained on |
| `lora_config.yaml` | Training settings for 16 GB of memory |
| `data/`, `adapters/` | Generated locally, git-ignored |

**About the starter pairs.** They were written for this project in an ASL-style gloss notation and **have not been reviewed by a fluent signer**. Treat them as a placeholder until someone fluent checks and extends them. Every pair must pass the generation constraint, and none may repeat a row of `benchmarks/glosses.jsonl`. `build_dataset.py` and `tests/test_finetune.py` enforce both. Training examples use exactly the chat the server sends at runtime (`build_messages`), including Qwen's empty thinking block, so training and serving cannot drift apart.

## Run it

All commands run from `ml-service/`. The model must already be in `models/Qwen3.5-2B`; see `MODEL_SELECTION.md`.

1. Build the data:

   ```bash
   .venv/bin/python finetune/build_dataset.py
   ```

2. Train. This takes about **an hour** on the M4 (300 steps; 58–62 minutes so far); keep the Mac plugged in.

   ```bash
   .venv/bin/mlx_lm.lora -c finetune/lora_config.yaml 2>&1 | tee finetune/adapters/qwen35-2b-gloss-r2/train.log
   ```

3. Serve the model with the adapter:

   ```bash
   .venv/bin/mlx_lm.server --model models/Qwen3.5-2B --adapter-path finetune/adapters/qwen35-2b-gloss-r2 --host 127.0.0.1 --port 8002
   ```

4. Evaluate on the benchmark and on the held-out test split:

   ```bash
   .venv/bin/python benchmarks/bench_generator.py --backend openai_compat --model default_model --cases benchmarks/glosses.jsonl --runs 3
   ```

   ```bash
   .venv/bin/python benchmarks/bench_generator.py --backend openai_compat --model default_model --cases finetune/data/test_glosses.jsonl
   ```

**Important:** request `default_model`, not the model path. `mlx_lm.server` attaches the adapter only to `default_model`. A request naming the path silently loads a second copy of the base model **without** the adapter. That happened in our first evaluation and gave outputs identical to the base model. For the service, set `GEN_MODEL=default_model` when the server has an adapter.

## Results (Apple M4 16 GB, mlx-lm 0.32.2, thinking off)

"Exact" means identical to the reference after lower-casing and dropping punctuation. It is strict: "Tomorrow it will rain." counts as a miss against "It will rain tomorrow." "Pass" means the model's output passed the constraint; otherwise the template was used. All reports are in `benchmarks/reports/` (`m4-qwen35-2b-*`).

### Round 2 (2026-10-26): 60 WH-question pairs added, 306 training rows, 300 steps

| Model | Benchmark (16 rows) | WH rows of benchmark (2) | New test split (27) | New test, rows neither adapter trained on (8) |
| --- | --- | --- | --- | --- |
| Base Qwen3.5-2B | 75% exact, 100% pass | 2/2 | 48% exact, 89% pass | 50% exact, 62% pass |
| Round 1 adapter | 75% exact, 94% pass | 1/2 | — (trained on 19 of these rows) | 50% exact, 75% pass |
| **Round 2 adapter** | **81% exact, 94% pass** | **2/2** | **78% exact, 100% pass** | **62% exact, 100% pass** |

- **Benchmark detail.** The round-2 benchmark figures cover 3 runs (48 requests), and the outputs were the same in every run.
- **Loss and resources.** Final test loss was 0.061 (round 1: 0.066). Training took 58 minutes, with a peak memory footprint of 14.2 GB out of 16 GB. Don't run other heavy apps while training.
- **Latency.** About 1.06 s p50, versus about 0.97 s for the base model.
- **Training log.** `adapters/qwen35-2b-gloss-r2/train.log` was kept, but `mlx_lm.lora` wrote only the final test loss to it, not per-step losses. The progress output apparently does not go through the pipe.

**What round 2 fixed**
- WH-questions are fronted again: "What is your name?", and on held-out rows "Where are you going?"-style questions.
- Round 1's gains are kept: "My name is Ana.", tense from time signs, "My head hurts."

**Still wrong**
- `IX-1 GO STORE TOMORROW` gives "I go store tomorrow." TOMORROW is dropped from the model's output, so the template is used. It fails the same way in all 3 runs.
- Without a time sign it now uses plain present tense ("I learn sign language.", where the reference has "I am learning…"). That is consistent with the training rule, so it may be the reference that should change.

**Caveats.** The clean comparison has only 8 rows, and one author wrote the training and test pairs, so these are small, optimistic numbers. A fluent signer still needs to review `pairs.tsv`.

**Verdict.** Round 2 is the best generator so far, and it beats the base model on the independent benchmark. Use it with `GEN_BACKEND=openai_compat`, `GEN_MODEL=default_model`, and `mlx_lm.server --adapter-path finetune/adapters/qwen35-2b-gloss-r2`. The template fallback still covers the rejected rows. To share the adapter with teammates, they need the same base model plus the 22 MB `adapters.safetensors` and `adapter_config.json`.

### Round 1 (2026-10-25): 244 training rows, 300 steps

| Model | Benchmark (16 rows): exact / pass | Round-1 held-out (30 rows): exact / pass |
| --- | --- | --- |
| Base | 75% / 100% | 60% / 80% |
| + LoRA, 100 steps | 56% / 69% | 63% / 77% |
| + LoRA, 200 steps | 69% / 81% | 70% / 90% |
| + LoRA, 300 steps | 75% / 94% | 80% / 93% |

Round 1 fixed tense and the name and possessive patterns, but it kept sign order in WH-questions ("Your name is what?"). That regression is why round 2 added WH-question pairs. Its held-out split was a seeded shuffle and is not comparable with round 2's hash-based split.
