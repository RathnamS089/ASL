# ml-service

The Python inference service for VISUALISER. It implements [docs/ML_CONTRACT.md](../docs/ML_CONTRACT.md).

## Current state

| Part | State |
| --- | --- |
| HTTP service (`/health`, `/v1/infer`, `/v1/generate`), internal token, mock mode, busy guard | Done, with tests |
| Generation constraint (`generation/constraints.py`) | Done, with tests |
| Template generator (deterministic fallback) | Done, with tests |
| OpenAI-compatible generator, for vLLM or llama.cpp `llama-server` | Done, tested against a fake server. **Not yet run against a real model.** |
| Generator benchmark (`benchmarks/bench_generator.py`) | Done. Template baseline only so far. |
| Recognizer | **Interface only.** The Recognition workstream fills it in at milestone 5. |

Model choice and vLLM notes: [MODEL_SELECTION.md](MODEL_SELECTION.md). Datasets: [docs/DATASETS.md](../docs/DATASETS.md).

## Run

The commands below are for macOS and Linux. On Windows, use `.venv\Scripts\python` and set environment variables with `$env:NAME="value"`.

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

## Windows on ARM

Record here which interpreter you used (`python -c "import platform; print(platform.machine())"`) and whether `pip install -e .[dev]` succeeded natively. The service's own dependencies are FastAPI, uvicorn and python-multipart. Recognition dependencies (video decoding, landmarks) must be checked separately.

| Date | Machine | Python arch | Install OK? | Tests | Notes |
| --- | --- | --- | --- | --- | --- |
| | | | | | |
