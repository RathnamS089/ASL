# Team assignments

Four owners, one per workstream. Write real names into the table once the team agrees on it. Each **interface** has exactly one producer and one consumer, and both must approve any change to it.

| # | Workstream | Owner | Code | Owns these interfaces |
| --- | --- | --- | --- | --- |
| 1 | Web frontend | _TBD_ | `web/` | Consumer of the browser API ([API_CONTRACT.md](API_CONTRACT.md)) |
| 2 | Go backend | _TBD_ | `backend-go/` | Producer of the browser API; consumer of the ML API ([ML_CONTRACT.md](ML_CONTRACT.md)) |
| 3 | Recognition | _TBD_ | `ml-service/recognition/` | Producer of `RecognitionResult` (inside ML_CONTRACT.md) |
| 4 | Language / inference | _TBD_ | `ml-service/` (server, `generation/`) | Producer of the ML API; consumer of `RecognitionResult` |

Shared: `contracts/` (all four), `docs/` (author of each doc + one reviewer). The existing iOS app has no owner yet (decision D5). Until someone owns it, nobody changes it except to keep it compatible.

## 1. Web frontend

**Responsibilities**
- **Camera lifecycle.** `getUserMedia` constraints, start and stop, releasing tracks when the user navigates away or the tab is hidden, and switching between front and back cameras.
- **Permissions.** States for prompt, granted, denied, unavailable and insecure-context. Each error name (`NotAllowedError`, `NotFoundError`, `NotReadableError`, `OverconstrainedError`, `SecurityError`) gets recovery copy.
- **Recording.** `MediaRecorder` with MIME type negotiation via `MediaRecorder.isTypeSupported`, a 10 s cap, a minimum duration, preview playback, and re-record.
- **API client.** One `TranslationClient` module. The base URL comes from `import.meta.env.VITE_API_BASE_URL`. It handles timeouts, aborting, typed errors that map to the error codes, and stale-response guards.
- **UI states.** Idle → camera-ready → recording → review → uploading → processing → result or error. Every state is reachable with the mock.
- **Layout and typography.** A responsive layout that works on phones first, in portrait and landscape. Kinetic typography is driven by `tokens` and `signs` timings, respects `prefers-reduced-motion`, and exposes the full sentence to screen readers.

**Deliverables**
- **M2.** Full UI against an in-browser mock that returns `contracts/examples/translation-response.json`.
- **M3.** The same UI against the mock Go endpoint over the LAN.
- **M8.** Device test matrix results.

**Tests:** Vitest unit tests for the state machine, the API client (with fetch mocked using the shared examples) and the recorder MIME negotiation. Manual device checklist.

## 2. Go backend

**Responsibilities**
- **API.** The versioned `/v1` routes and a single error envelope.
- **Request handling.** Request IDs, structured logs (no clip bytes or result text), and limits: body cap, concurrency slot, rate limit.
- **Upload validation.** Multipart parsing, magic-byte sniffing, metadata schema, temp-file lifecycle.
- **Orchestration.** A bounded inference queue (default concurrency 1), deadlines, and mapping ML errors to API errors.
- **ML client.** Calls the Python service with the internal token.
- **Supabase (M7).** JWT verification, a history table with row-level security, and service-role key handling (server-only).
- **Config.** Narrow CORS from env and all other env-based configuration.

**Deliverables**
- **M3.** Mock `POST /v1/translations` returning the shared example.
- **M4.** The real ML client against the mock Python service.
- **M7.** Auth and history.

**Tests:** `net/http/httptest` table tests for every error code, oversize bodies, wrong magic bytes, missing parts, timeouts (using a fake ML server), concurrency limits, and a JSON round trip of the shared examples.

## 3. Recognition

**Responsibilities**
- **Datasets.** Research and licence review for datasets in the language chosen under D1, followed by the MVP vocabulary choice.
- **Vision pipeline.** Decoding, frame sampling, and pose or hand landmark extraction. Check that the chosen library has macOS arm64 builds and runs on the M4 Mac before committing to it.
- **Temporal model.** Isolated-sign classification first; multi-sign segmentation only if D8 requires it.
- **Evaluation.** A held-out split separated by signer, top-1/top-5 accuracy, a confusion matrix, per-signer breakdown, and latency per clip on the M4 Mac.
- **Output.** `RecognitionResult` exactly as ML_CONTRACT.md defines it, including honest confidence scores.

**Deliverables**
- **M1.** Dataset and licence shortlist plus a vocabulary proposal.
- **M5.** Recognizer behind the `Recognizer` interface.
- **M9.** Evaluation report with real numbers only.

**Tests:** pytest for decoding edge cases (truncated, zero-length, rotated, variable frame rate), output invariants (ordering, bounds, confidence range), and a small fixture clip committed only if its licence allows.

## 4. Language / inference

**Responsibilities**
- **ML service.** The Python HTTP service: health and readiness, the internal token, mock mode, model loading from `ML_MODEL_DIR`.
- **Generator adapter.** A `Generator` interface turns glosses into a sentence and tokens. There is a deterministic template implementation first, then a constrained model.
- **Constraints.** Structured output validation: no content words that do not come from a recognized gloss, and fallback to the template on failure.
- **Benchmarks.** Candidate generators on the M4 Mac: load time, memory, latency per request, and output quality on a fixed gloss test set. Report the runtime and device (for example MLX on Metal), and claim no acceleration that was not measured.
- **Integration.** Wiring recognition into generation inside the service.

**Deliverables**
- **M4.** Mock Python service returning `contracts/examples/ml-infer-response.json`.
- **M6.** Constrained generator.
- **M9.** Benchmark report.

**Tests:** pytest for the HTTP contract (shared examples), the generator constraint validator, fallback behaviour, and timeouts.

## Review pairing

Each change to a contract needs approval from both sides of it:

| Change touches | Required reviewers |
| --- | --- |
| `docs/API_CONTRACT.md`, `contracts/examples/translation-*`, `error-*` | Web + Go |
| `docs/ML_CONTRACT.md`, `contracts/examples/ml-*` | Go + Language/inference |
| `RecognitionResult` section | Recognition + Language/inference |
| Security-relevant Go code (auth, upload, CORS) | Go + any one other owner |

## Cross-cutting duties

| Duty | Primary | Backup |
| --- | --- | --- |
| LAN/HTTPS dev setup ([DEVELOPMENT_SETUP.md](DEVELOPMENT_SETUP.md)) | Web | Go |
| M4 Mac model-host environment | Language/inference | Recognition |
| Shared `contracts/` checks | Go | Web |
| Physical device testing (M8) | Web | everyone brings a phone |
| Latency and resource measurement (M9) | Language/inference | Recognition |
