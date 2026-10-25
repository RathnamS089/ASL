# ml-service

The Python inference service for VISUALISER. It implements [docs/ML_CONTRACT.md](../docs/ML_CONTRACT.md).

## Current state

| Part | State |
| --- | --- |
| HTTP service (`/health`, `/v1/infer`, `/v1/generate`), internal token, mock mode, busy guard | Done, with tests |
| Generation constraint (`generation/constraints.py`) | Done, with tests |
| Template generator (deterministic fallback) | Done, with tests |
| OpenAI-compatible generator (MLX server, llama.cpp or vLLM) | Done. Measured with Qwen3.5-2B on the M4 through `mlx_lm.server`. |
| Generator benchmark (`benchmarks/bench_generator.py`) | Done. Template and Qwen3.5-2B reports in `benchmarks/reports/`. |
| Recognizer | **Interface only.** The Recognition workstream fills it in at milestone 5. |

Model choice and vLLM notes: [MODEL_SELECTION.md](MODEL_SELECTION.md). Datasets: [docs/DATASETS.md](../docs/DATASETS.md).

## Run

The model host is an Apple M4 Mac (16 GB). The commands below are for macOS.

```bash
cd ml-service
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q
cp .env.example .env
```

Edit `.env` and set `ML_INTERNAL_TOKEN`. To start the service in mock mode:

```bash
ML_INTERNAL_TOKEN=dev ML_MOCK=1 .venv/bin/uvicorn visualiser_ml.app:create_app --factory --host 127.0.0.1 --port 8001
```

Only ever bind it to `127.0.0.1`. Go is the only client.

## Model host

| Date | Machine | Python | Install OK? | Tests | Notes |
| --- | --- | --- | --- | --- | --- |
| 2026-10-25 | Apple M4, 16 GB, macOS | 3.12 (arm64) | Yes, including `mlx-lm==0.32.2` | 34 passed | Qwen3.5-2B served by `mlx_lm.server` on Metal; see MODEL_SELECTION.md |

To serve the generator, see [MODEL_SELECTION.md](MODEL_SELECTION.md#running-the-model-on-a-mac-apple-silicon).
