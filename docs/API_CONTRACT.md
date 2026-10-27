# Browser ↔ Go API contract (v1)

Status: **draft for agreement at milestone 1**. Producer: Go backend. Consumers: web frontend and the existing iOS app.
The canonical examples are in `contracts/examples/`, and every team's tests use them. If this document and an example disagree, fix both in the same change.

## Conventions

- **Base URL.** Go serves `/health` and `/v1/...` at its root. The web app calls `${VITE_API_BASE_URL}`, which is `/api` in development. Vite proxies `/api/*` to Go and strips the `/api` prefix. The iOS app is configured with Go's own base URL.
- **JSON format.** UTF-8 JSON, `snake_case` keys. Timestamps use RFC 3339 UTC (`2026-10-25T12:00:00Z`). IDs are opaque strings, so clients must not parse them.
- **Clip-relative times.** All times are `*_seconds` floats measured from the first decoded frame of the clip. Durations are `*_ms` integers.
- **Forward compatibility.** Clients **must ignore unknown fields**. Adding fields is non-breaking. Removing or renaming a field, or changing a type or meaning, requires `/v2`.
- **Request IDs.** Every response carries an `X-Request-ID` header. Go echoes the client's value if it is a UUID, otherwise it generates one. Error bodies repeat it.
- **Authentication.** `Authorization: Bearer <Supabase access token>` when required (see D2). Go verifies the JWT signature, `exp` and `aud`. The browser never holds a service-role key.

## `GET /health`

Liveness only. It does not check dependencies, which keeps the existing iOS "Test connection" behaviour working.

```json
200 { "status": "ok", "version": "0.1.0" }
```

## `GET /health/ready`

Reports whether translation can succeed right now: the ML service is reachable and its models are loaded.

```json
200 { "status": "ready", "inference": "ok", "mock": false }
503 { "status": "not_ready", "inference": "unavailable", "mock": false }
```

## `POST /v1/translations`

Uploads one short clip and returns the translation **synchronously**.

### Request: `multipart/form-data` (canonical)

| Part | Required | Type | Rules |
| --- | --- | --- | --- |
| `clip` | yes | file | Exactly one. Container sniffed from bytes: WebM/Matroska (`1A 45 DF A3`) or ISO-BMFF MP4/MOV (`ftyp` at byte offset 4). The part's `Content-Type` and filename are informational only; the filename is never used on disk. |
| `metadata` | no (recommended) | `application/json` text | ≤ 4 KiB. Schema below. Unknown keys are ignored. |

No other parts are allowed; an unexpected part returns `400 invalid_request`.

**`mode`** (optional, default `"signs"`):
- **`"signs"`:** whole ASL signs (the 250-sign vocabulary), turned into a sentence by the generator.
- **`"letters"`:** fingerspelling. Each held letter A–Z becomes one entry in `signs`, and `sentence` is the spelled word, with `generation.source: "fingerspelling"`.
- **Anything else:** `400 invalid_request`.

`metadata` (example: `contracts/examples/translation-request-metadata.json`):

```json
{
  "client_request_id": "6f1c8a52-4f0e-4a4e-9a51-3e2b7d1c9a10",
  "sign_language": "ase",
  "mode": "signs",
  "recording": {
    "started_at": "2026-10-25T12:00:00Z",
    "duration_ms": 4200,
    "mime_type": "video/webm;codecs=vp8",
    "width": 640,
    "height": 480,
    "frame_rate": 30,
    "facing_mode": "user"
  },
  "client": { "platform": "web", "app_version": "0.1.0", "user_agent_family": "chrome-android" }
}
```

- **`sign_language`.** An ISO 639-3 sign-language code (`ase` for ASL, `ins` for Indian SL, `bfi` for BSL, and so on). The server rejects any value other than the one configured language (D1), returning `422 unsupported_sign_language`. If the field is omitted, the server uses its configured language.
- **`recording.duration_ms`.** The client's own measurement, used only for early rejection. The ML service measures the authoritative duration after decoding.
- **`recording.started_at`.** Client clock, informational only, never trusted for ordering.

**Compatibility path (D5).** If the iOS client is kept, Go also accepts `Content-Type: video/mp4 | video/quicktime | video/x-m4v | application/octet-stream` with the raw clip as the body and no metadata. The same sniffing and limits apply.

### Limits (proposed, D6)

| Limit | Value | Enforced by | Error |
| --- | --- | --- | --- |
| Request body | 20 MiB | Go `http.MaxBytesReader` | `413 payload_too_large` |
| Clip duration | 0.5 s – 10.0 s | Client (UX), ML service (authoritative) | `422 clip_too_short` / `clip_too_long` |
| Resolution | ≤ 1280×720 recommended (client requests 640×480 ideal) | Client; ML may downscale | — |
| Concurrent inferences | 1 (env `INFERENCE_CONCURRENCY`) | Go semaphore | queued |
| Queue depth | 4 waiting requests (env `INFERENCE_QUEUE_DEPTH`) | Go | `503 busy` with `Retry-After` |
| Rate | 10 translations / minute per user or IP (env) | Go | `429 rate_limited` with `Retry-After` |

At 640×480 and 30 fps, a 10 s WebM clip from `MediaRecorder` is typically a few MB, which leaves headroom under the 20 MiB cap. Verify this on real devices at M8.

### Timeouts

| Hop | Timeout |
| --- | --- |
| Go `ReadHeaderTimeout` | 10 s |
| Go `ReadTimeout` (whole upload, slow Wi-Fi) | 30 s |
| Waiting for an inference slot | 20 s → `503 busy` |
| Go → Python call | 45 s → `504 inference_timeout` |
| Go `WriteTimeout` | 100 s |
| Browser `AbortController` for the whole request | 110 s (the iOS app uses 120 s) |

Each outer timeout is longer than the sum of the inner ones, so clients always receive a typed error rather than a dropped connection. If the client aborts, Go cancels the context and stops the ML call.

### Response `200` (example: `contracts/examples/translation-response.json`)

```json
{
  "id": "tr_01JBK6Q2Z8X4M5N7P9R1S3T5V7",
  "created_at": "2026-10-25T12:00:05Z",
  "sentence": "Hello, my friend.",
  "signs": [
    { "label": "HELLO",  "start_seconds": 0.40, "end_seconds": 1.30, "confidence": 0.91 },
    { "label": "MY",     "start_seconds": 1.45, "end_seconds": 1.90, "confidence": 0.62 },
    { "label": "FRIEND", "start_seconds": 2.05, "end_seconds": 3.10, "confidence": 0.84 }
  ],
  "tokens": [
    { "text": "Hello,",  "sign_index": 0,    "emphasis": "strong" },
    { "text": "my",      "sign_index": 1,    "emphasis": "low_confidence" },
    { "text": "friend.", "sign_index": 2,    "emphasis": "normal" }
  ],
  "sign_language": "ase",
  "low_confidence": false,
  "generation": { "source": "model", "constrained": true },
  "is_mock": false,
  "models": { "recognizer": "isolated-gru@0.1.0", "generator": "template@0.1.0" },
  "timings_ms": { "queue": 0, "inference": 1340, "total": 2210 }
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `id`, `sentence`, `signs[].label/start_seconds/end_seconds`, `is_mock` | as in the existing iOS DTO | **Required and stable.** `sentence` is never empty: an empty result is an error instead (see `no_signs_detected`). |
| `signs[].confidence` | number 0–1 or `null` | The model's score for the top label. **Not a calibrated probability** unless the recognizer's model card says so. `null` if unavailable. Never invented. |
| `tokens[]` | array | Drives the kinetic typography. Joining the `text` values with single spaces gives `sentence`. `sign_index` is the index into `signs`, or `null` for function words the generator inserted. `emphasis` is one of `normal`, `strong`, `low_confidence`. |
| `low_confidence` | bool | True when the recognizer's overall score is below its configured threshold. The UI should suggest re-recording. |
| `generation.source` | `model` \| `template` \| `mock` \| `fingerspelling` | `template` means the constrained model was unavailable or its output was rejected. `fingerspelling` means `mode: "letters"`: the sentence is the letters themselves, with no language model. |
| `mode` | `signs` \| `letters` | Echoes the request's mode. |
| `models`, `timings_ms` | object | For display in debug mode and for M9 measurements. Their keys may grow. |

Signs are ordered by `start_seconds`, do not overlap, satisfy `0 ≤ start ≤ end ≤ clip duration`, and have non-empty labels. These invariants match `TranslationResponse.validated()` in `VisualiserCore`.

## Error envelope (all non-2xx)

```json
{
  "error": {
    "code": "clip_too_long",
    "message": "The clip is 12.4 s long. Record 10 seconds or less.",
    "request_id": "0b7c2a8e-1d7e-4a3c-8f55-0e6d2b9a4c11",
    "retryable": false,
    "details": { "max_seconds": 10.0, "actual_seconds": 12.4 }
  }
}
```

`message` is safe to show to users but carries no localisation guarantee. Clients branch on `code`. `details` is optional and specific to each code.

| HTTP | `code` | Retryable | Meaning / client action |
| --- | --- | --- | --- |
| 400 | `invalid_request` | no | Malformed multipart, missing `clip`, an extra part, or invalid `metadata` JSON |
| 401 | `unauthorized` | no | Missing, expired or invalid token. Sign in again. |
| 403 | `forbidden` | no | Authenticated, but not allowed (for example, another user's history item) |
| 404 | `not_found` | no | Unknown route or ID |
| 413 | `payload_too_large` | no | Over 20 MiB. Record a shorter clip. |
| 415 | `unsupported_media_type` | no | Bytes are not WebM or MP4/MOV |
| 422 | `clip_too_short` / `clip_too_long` | no | Duration outside 0.5–10 s |
| 422 | `undecodable_clip` | no | The container sniffed correctly but could not be decoded |
| 422 | `no_signs_detected` | no | Valid clip, but no sign passed the threshold. Suggest framing and lighting tips. |
| 422 | `unsupported_sign_language` | no | Not the configured language |
| 429 | `rate_limited` | yes | Wait for `Retry-After` |
| 500 | `internal` | yes | Bug. Report the `request_id`. |
| 502 | `inference_failed` | yes | The ML service returned an internal error |
| 503 | `busy` / `inference_unavailable` | yes | The queue is full, or ML is down. Wait for `Retry-After` when it is present. |
| 504 | `inference_timeout` | yes | ML took longer than 45 s |

## History (milestone 7, only if D3 keeps accounts)

All history routes require auth. Rows are scoped to the token's `sub` by Postgres row-level security, and Go also checks ownership. **Only text results are stored, never clips** (D4).

- `GET /v1/translations?limit=20&cursor=<opaque>` → `{ "items": [TranslationResponse…], "next_cursor": "…" | null }`
- `GET /v1/translations/{id}` → `TranslationResponse`
- `DELETE /v1/translations/{id}` → `204`

## CORS

- **Development.** Not needed, because the browser and `/api` share the Vite origin.
- **When needed.** Set `CORS_ALLOWED_ORIGINS` to a comma-separated list of exact origins. No wildcards and no reflecting `Origin` back.
- **Allowed values.** Methods `GET, POST, DELETE, OPTIONS`. Request headers `Authorization, Content-Type, X-Request-ID`. Exposed headers `X-Request-ID, Retry-After`.
- **Credentials.** Cookies are not used; tokens travel in the header.

## Reserved for later (do not implement yet)

- **Async processing.** `POST /v1/translations` with `Prefer: respond-async` → `202` + `Location: /v1/translations/{id}`, then the client polls `GET` for `status: queued|processing|done|failed`. Adopt this only if M9 shows synchronous requests hitting the timeouts.
- **Live sessions.** `GET /v1/sessions` (WebSocket) for continuous translation, which needs its own contract document.
