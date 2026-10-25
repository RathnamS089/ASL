# VISUALISER: team instructions

VISUALISER is a **web app**. Someone opens the site on a phone or laptop, allows the camera, records a short sign-language clip, and gets the recognised text back as animated (kinetic) typography.

```text
Browser (React)  ──HTTPS──▶  Go API  ──localhost──▶  Python ML service  ──▶  recognizer + text generator
```

Read these first, in order:
1. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how the pieces fit together
2. [docs/API_CONTRACT.md](docs/API_CONTRACT.md): what the browser sends to Go and what comes back
3. [docs/ML_CONTRACT.md](docs/ML_CONTRACT.md): what Go sends to Python and what comes back
4. [docs/DEVELOPMENT_SETUP.md](docs/DEVELOPMENT_SETUP.md): running everything on one Wi-Fi with phones (HTTPS, firewall)
5. [docs/INTEGRATION_PLAN.md](docs/INTEGRATION_PLAN.md): milestones, risks and open decisions

## Rules for everyone

- **`main` must always work.** Never commit straight to `main`. Make a branch (`web/camera-ui`, `go/mock-endpoint`, …), open a pull request, and merge only when tests pass and one other member has reviewed it.
- **Small pull requests.** One thing per PR.
- **Contracts are shared.** If you need to change a JSON field, change `docs/*_CONTRACT.md` and `contracts/examples/` in their own PR, and get the member on the other side to approve it.
- **Before every PR**, run:

  ```bash
  python3 contracts/check_examples.py
  ```

- **Never commit** `.env` files, certificates, model weights, datasets or recorded clips. `.gitignore` already blocks them.
- **No made-up numbers.** Accuracy and speed numbers must come from a script someone actually ran, and the results should say on which machine.

## Who does what

Replace the names once agreed. Tick items off in your PRs.

### Member 1: Web frontend (`web/`)

Milestone 2: camera UI with fake results.
- [ ] Create `web/` with Vite + React + TypeScript + Tailwind. Add Vitest.
- [ ] Camera screen: start and stop the camera, switch between front and back, and show a preview. Use `playsinline muted` on the `<video>`.
- [ ] Permission states: not asked, allowed, denied, no camera, camera busy, and **not HTTPS**. Each one gets a friendly message (see DEVELOPMENT_SETUP.md).
- [ ] Recorder: `MediaRecorder` with a 10-second limit and a countdown. After recording, show a replay with *Re-record* and *Submit* buttons.
- [ ] Screens for Processing, Result and Error. The result uses `contracts/examples/translation-response.json` as fake data.
- [ ] Kinetic typography: animate the words from `tokens`, using `signs` for timing. Words with `low_confidence` look different. Respect *reduce motion*.
- [ ] Make it work on a phone screen first, in portrait and landscape.

Milestone 3: talk to Go.
- [ ] One API module, `translationClient.ts`, that reads `VITE_API_BASE_URL`. It handles a 110 s timeout, cancel, and every error `code` in API_CONTRACT.md.
- [ ] `vite.config.ts` with LAN access, HTTPS from env, and the `/api` proxy to Go (template in DEVELOPMENT_SETUP.md).
- [ ] Test on one iPhone and one Android phone over the Wi-Fi.

### Member 2: Go backend (`backend-go/`)

Milestone 3: fake endpoint.
- [ ] Create `backend-go/` (Go modules, `net/http` only, config from env, see DEVELOPMENT_SETUP.md).
- [ ] `GET /health` and `GET /health/ready`.
- [ ] `POST /v1/translations` accepting multipart `clip` + `metadata`:
  - 20 MiB cap (`http.MaxBytesReader`)
  - check the file's first bytes (WebM or MP4/MOV), not just its name
  - save to a temp file and always delete it
  - with `MOCK_TRANSLATION=1`, return the example response
- [ ] The single error format from API_CONTRACT.md, and `X-Request-ID` on every response.
- [ ] `httptest` tests for every error code.

Milestone 4: call Python.
- [ ] ML client: multipart to `ML_BASE_URL/v1/infer` with `X-Internal-Token` and a 45 s timeout.
- [ ] One inference at a time, with a small queue. When it's full, return `503 busy` with `Retry-After`.
- [ ] Map Python's answers to API errors. Empty `segments` → `422 no_signs_detected`.

Milestone 7 (only if we keep accounts): Supabase JWT check, a history table with row-level security, and the service-role key **only** in Go's `.env`.

### Member 3: Recognition (`ml-service/visualiser_ml/recognition/`)

Milestone 1:
- [ ] Help the team choose the sign language (D1). Use [docs/DATASETS.md](docs/DATASETS.md) and check each licence.
- [ ] Propose a first vocabulary of 20–50 signs and commit it as `ml-service/vocabulary/<lang>.txt`.
- [ ] Check that video decoding and hand/pose landmark libraries install on the **Windows on ARM laptop**. Record the result in `ml-service/README.md`.

Milestone 5:
- [ ] Turn a clip into landmark sequences, then use a small temporal model to produce signs with times and confidence.
- [ ] Implement the `Recognizer` interface in `recognition/__init__.py`. The output must follow ML_CONTRACT.md: times in seconds, sorted, no overlaps, and confidence between 0 and 1.
- [ ] Test on signers who were **not** in training, and on clips the team records on phones.
- [ ] Milestone 9: an evaluation report with real accuracy, a confusion matrix, per-signer results and time per clip.

### Member 4: Language / inference (`ml-service/`, generator)

Done (in `main`):
- [x] Python service: `/health`, `/v1/infer`, `/v1/generate`, internal token, mock mode, one-at-a-time guard
- [x] Rule that stops the text generator inventing words (`generation/constraints.py`)
- [x] Template generator that always works (fallback)
- [x] Adapter for **vLLM** or **llama.cpp `llama-server`** (OpenAI-compatible), with thinking mode off and a fallback if the model breaks the rule
- [x] Benchmark script and 16 test sentences (`ml-service/benchmarks/`)
- [x] Model and dataset research: [ml-service/MODEL_SELECTION.md](ml-service/MODEL_SELECTION.md), [docs/DATASETS.md](docs/DATASETS.md)
- [x] 32 passing tests (`cd ml-service && .venv/bin/python -m pytest -q`)

Still to do:
- [ ] On the Snapdragon laptop: install the service and fill in the Windows-on-ARM table in `ml-service/README.md`.
- [ ] Install `llama-server` (native ARM64). Download **by hand** one candidate model (start with Qwen3.5-2B, 4-bit GGUF) after checking its licence.
- [ ] Run `benchmarks/bench_generator.py` for the template and each candidate, then write the results into MODEL_SELECTION.md.
- [ ] Choose: template only, or a model (decision D9).
- [ ] When Member 3's recognizer is ready, connect it in `app.py` and test the full pipeline.

## Running what exists today

```bash
python3 contracts/check_examples.py
```

```bash
cd ml-service && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]' && .venv/bin/python -m pytest -q
```

To start the ML service in mock mode:

```bash
cd ml-service && ML_INTERNAL_TOKEN=dev ML_MOCK=1 .venv/bin/uvicorn visualiser_ml.app:create_app --factory --host 127.0.0.1 --port 8001
```

## Decisions the team still has to make

See the table at the end of [docs/INTEGRATION_PLAN.md](docs/INTEGRATION_PLAN.md#unresolved-decisions). The most urgent:
- **D1** which sign language
- **D2** whether login is needed to translate
- **D6** clip limits
- **D8** one sign per clip, or several
