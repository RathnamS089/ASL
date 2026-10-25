# Go ↔ Python inference contract (v1)

Status: **draft for agreement at milestone 1**. Producer: Language/inference owner (service) and Recognition owner (`RecognitionResult`). Consumer: Go backend.
Examples: `contracts/examples/ml-*.json`.

## Deployment rules

- **Address.** Binds to `ML_LISTEN_HOST=127.0.0.1` and `ML_LISTEN_PORT=8001` by default. Do **not** bind it to `0.0.0.0` or open a firewall port for it. Only Go calls it.
- **Internal token.** Every request except `GET /health` must carry the header `X-Internal-Token: <ML_INTERNAL_TOKEN>`. Compare it in constant time and return `401` if it does not match. The token lives in each service's `.env` file and is never committed.
- **Model weights.** Loaded from `ML_MODEL_DIR` (default `ml-service/models/`, git-ignored). The service must **never download weights on startup**. If they are missing, it starts in not-ready state and `/health` says why.
- **Mock mode.** `ML_MOCK=1` returns `contracts/examples/ml-infer-response.json` deterministically after `ML_MOCK_DELAY_MS`, with no models loaded. The output must say `"mock": true`.
- **Concurrency.** The service processes one inference at a time. Go is responsible for queueing, so the service does not need its own queue. If it receives a second concurrent request, it may return `503 busy`.

## `GET /health`

```json
200 {
  "status": "ready",
  "mock": false,
  "models": {
    "recognizer": { "name": "isolated-gru", "version": "0.1.0", "loaded": true },
    "generator":  { "name": "template",     "version": "0.1.0", "loaded": true }
  },
  "runtime": { "python": "3.12.x", "machine": "ARM64", "execution_provider": "cpu" }
}
```

`status` is `ready`, `loading` or `not_ready`, with a `reason`. `runtime` reports what the process actually detected, for example from `platform.machine()` and the providers the ONNX or other runtime says it is using. Use it to stop anyone assuming acceleration that isn't there.

## `POST /v1/infer`

### Request: `multipart/form-data`

| Part | Required | Content |
| --- | --- | --- |
| `request` | yes | JSON, schema below |
| `clip` | yes | The clip bytes exactly as Go validated them (WebM or MP4/MOV) |

Go sends the clip rather than extracted frames for three reasons. Go does not need a video decoder, browser codecs vary, and only the ML service knows the frame sampling the model needs. A future streaming mode could send landmarks or frames under a separate endpoint.

`request` (example: `contracts/examples/ml-infer-request.json`):

```json
{
  "request_id": "0b7c2a8e-1d7e-4a3c-8f55-0e6d2b9a4c11",
  "sign_language": "ase",
  "clip": { "container": "webm", "size_bytes": 1843200, "client_duration_ms": 4200 },
  "limits": { "min_seconds": 0.5, "max_seconds": 10.0, "max_signs": 8 },
  "options": { "generate": true, "include_alternatives": false }
}
```

Go sets `limits`, so there is one source of truth: Go reads them from its env and the ML service enforces whatever it receives. If `options.generate` is `false`, the service returns recognition only (`generation: null`). This exists for recognition evaluation runs.

### Response `200` (example: `contracts/examples/ml-infer-response.json`)

```json
{
  "request_id": "0b7c2a8e-1d7e-4a3c-8f55-0e6d2b9a4c11",
  "mock": false,
  "recognition": {
    "duration_seconds": 4.17,
    "frames_decoded": 125,
    "frames_used": 63,
    "fps": 30.0,
    "segments": [
      { "label": "HELLO", "start_seconds": 0.40, "end_seconds": 1.30, "confidence": 0.91, "alternatives": [] }
    ],
    "overall_confidence": 0.79,
    "low_confidence": false
  },
  "generation": {
    "text": "Hello, my friend.",
    "tokens": [ { "text": "Hello,", "segment_index": 0, "emphasis": "strong" } ],
    "source": "model",
    "constrained": true,
    "rejected_reason": null
  },
  "models": { "recognizer": { "name": "isolated-gru", "version": "0.1.0" }, "generator": { "name": "template", "version": "0.1.0" } },
  "timings_ms": { "decode": 210, "landmarks": 980, "recognition": 120, "generation": 15, "total": 1340 }
}
```

**A clip with no confident signs is not an error.** The service returns `200` with `segments: []` and `generation: null`. Go maps that to the public error `422 no_signs_detected`. This keeps the ML service's output a faithful record of what the model saw.

Go maps the ML response to the public API as follows:

| ML field | Public field |
| --- | --- |
| `recognition.segments[]` | `signs[]` (fields: `label`, `start_seconds`, `end_seconds`, `confidence`) |
| `generation.text` | `sentence` |
| `generation.tokens[].segment_index` | `tokens[].sign_index` |
| `recognition.low_confidence` | `low_confidence` |
| `generation.source` / `constrained` | `generation.source` / `constrained` |
| `mock` | `is_mock` |
| `models.*.name@version` | `models.*` |
| `timings_ms.total` | `timings_ms.inference` |

### Errors

The service uses the same envelope as the public API (`{ "error": { "code", "message", "request_id", "retryable", "details" } }`).

| HTTP | `code` | Go maps to |
| --- | --- | --- |
| 400 | `invalid_request` | 500 `internal`: a malformed request from Go is a Go bug |
| 401 | `unauthorized` | 500 `internal`: the token is misconfigured |
| 422 | `undecodable_clip` / `clip_too_short` / `clip_too_long` / `unsupported_sign_language` | same code, 422 |
| 503 | `models_not_loaded` / `busy` | 503 `inference_unavailable` / `busy` |
| 500 | `internal` | 502 `inference_failed` |
| timeout or connection refused | — | 504 `inference_timeout` / 503 `inference_unavailable` |

The service never puts stack traces or file paths in `message`. They belong in its own log, keyed by `request_id`.

## Invariants (checked by `contracts/check_examples.py` and by each side's tests)

1. **Timestamps.** Times are seconds relative to the first decoded frame (presentation timestamps, not wall clock), within `[0, duration_seconds]`, with `start ≤ end`.
2. **Ordering.** Segments are sorted by `start_seconds` and do not overlap. Labels are non-empty uppercase glosses from the vocabulary file that ships with the model.
3. **Confidence.** `confidence` and `overall_confidence` are in `[0, 1]` or `null`. They are raw model scores, typically softmax over the vocabulary. If calibration is done, the model card must say so and include the reliability measurement.
4. **Low confidence.** `low_confidence` uses the threshold `ML_LOW_CONFIDENCE_THRESHOLD`, which is reported in the model card and chosen from validation data at M9, not guessed.
5. **Token mapping.** Each `segment_index` is a valid index into `segments` or `null`. Joining `tokens[].text` with single spaces gives `text`.
6. **Generation constraint.** Every content word in `text` must come from a recognized segment. Only function words, punctuation and inflection may be added. The validator rejects anything else, and the service falls back to the deterministic template, setting `source: "template"` and the `rejected_reason`.

## In-process interfaces inside `ml-service`

These let Recognition and Language/inference work independently, and either side can be swapped for a fake in tests.

```python
class Recognizer(Protocol):
    def recognize(self, clip_path: Path, *, sign_language: str, limits: Limits) -> RecognitionResult: ...

class Generator(Protocol):
    def generate(self, segments: Sequence[Segment], *, sign_language: str, target_language: str = "en") -> GenerationResult: ...
```

`RecognitionResult` and `GenerationResult` are dataclasses or Pydantic models with exactly the `recognition` and `generation` objects above. Their JSON form is the contract.

## Windows on ARM notes (to verify, not assumptions)

- **Python architecture.** Python is available as native ARM64 and as x64, which runs under emulation. Before choosing, check that every dependency (video decoding, landmark extraction, the model runtime, the HTTP server) installs and runs under the chosen interpreter. Record the result in `ml-service/README.md`.
- **Accelerators.** Use of the NPU or GPU (for example through an ONNX Runtime execution provider) is an **experiment for M9**. Until a benchmark shows it, the contract and the docs say `execution_provider: "cpu"`.
- **Generator runtime.** If the generator is a local language model, pick a runtime and model size only after measuring memory and latency on the actual laptop. The template generator is the guaranteed fallback.
