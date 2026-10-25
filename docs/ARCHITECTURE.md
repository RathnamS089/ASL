# VISUALISER architecture

Status: **proposal for team review** (milestone 1). Nothing described under `web/`, `backend-go/` or `ml-service/` exists yet.

VISUALISER turns a short recorded sign-language clip into English text and renders the text with kinetic typography. The MVP is short clips: Start camera → Preview → Record → Stop → Submit → Processing → Result. Continuous live translation is a later goal, and the design leaves room for it without building it now.

## What already exists

The repository already contains a **native SwiftUI iOS client** (`Visualiser/`, `VisualiserCore/`, `Visualiser.xcodeproj`). It imports a video from Photos (it does not use the camera), runs a mock translation, and plays the sentence back as kinetic typography. It also has an untested "Real API" adapter for a provisional contract:

- `GET {base}/health`
- `POST {base}/v1/translations` with the **raw video as the request body** (not multipart)
- JSON response `{ id, sentence, signs[{label, start_seconds, end_seconds}], is_mock }`

The contracts in [API_CONTRACT.md](API_CONTRACT.md) keep that response shape. New fields are additive, and the Swift decoder ignores unknown keys. Whether Go also accepts the raw-body upload is decision **D5** in [INTEGRATION_PLAN.md](INTEGRATION_PLAN.md#unresolved-decisions).

The iOS project stays where it is at the repository root. Moving it into `ios/` would require changing Xcode project paths, so that is left as decision D11.

## Components

```text
 Phone / laptop browser                  Laptop (Windows on ARM, Snapdragon X)
┌──────────────────────────┐   HTTPS   ┌───────────────────────────────────────────────┐
│ web/  React + TS + Vite  │──────────▶│ Vite dev server :5173 (HTTPS, LAN)            │
│  camera, recorder,       │  /api/*   │   └─ proxy /api/* ─▶ backend-go :8080         │
│  API client, typography  │           │                      (loopback in dev)        │
└──────────────────────────┘           │                         │ multipart, loopback │
                                       │                         ▼                     │
 iOS app (existing, optional)          │      ml-service :8001  (127.0.0.1 only)       │
 ─────── HTTPS / .local ──────────────▶│      decode → landmarks → recognizer          │
                                       │             → constrained generator           │
                                       │      model weights: ml-service/models/        │
                                       └───────────────────────────────────────────────┘
                                                         │ (milestone 7, optional)
                                                         ▼
                                       Supabase Auth + PostgreSQL (hosted)
```

| Component | Language | Listens on (dev) | Reachable from | Owner |
| --- | --- | --- | --- | --- |
| `web/` | React, TypeScript, Vite, Tailwind, Framer Motion or CSS | `0.0.0.0:5173` over HTTPS | LAN phones | Web frontend |
| `backend-go/` | Go, `net/http` | `127.0.0.1:8080` by default; LAN only if a native client needs it | Vite proxy, optionally the iOS app | Go backend |
| `ml-service/` | Python HTTP service | `127.0.0.1:8001` | Go only | Recognition + Language/inference |
| Supabase | hosted | — | Go (service role), browser (anon key only) | Go backend |

### Why the browser talks only to Vite in development

- **One origin.** The page and `/api` share an origin, so development needs no CORS and no mixed-content workaround. An HTTPS page cannot call a plain-HTTP Go server on another port.
- **One certificate.** Only Vite needs a LAN TLS certificate, which keeps the phone camera setup to a single trusted origin.
- **Small exposure.** Go and Python stay on loopback, and only port 5173 needs a firewall rule.

In production a reverse proxy (or Go itself) plays Vite's role. Production hosting is out of scope for the MVP (D12).

## Request flow (MVP)

1. **Browser.** `getUserMedia` starts a preview, and `MediaRecorder` records a clip of up to 10 s. Chrome on Android usually produces `video/webm`, while Safari on iOS produces `video/mp4`. The client enforces the duration limit, shows a preview, and lets the user re-record.
2. **Submit.** The browser sends `POST /api/v1/translations` (multipart: `clip` plus a `metadata` JSON part), with `Authorization: Bearer <Supabase access token>` when auth is enabled.
3. **Go.**
   - Caps the body with `http.MaxBytesReader` and parses the multipart stream.
   - Sniffs the container from magic bytes rather than trusting `Content-Type`.
   - Spools the clip to a temporary file and validates the metadata.
   - Waits for a free inference slot (only one by default, because the laptop serves everyone).
   - Calls `ml-service` with a deadline.
4. **Python.**
   - Decodes the clip and extracts pose and hand landmarks.
   - Runs the recognizer to get a sequence of gloss segments with timestamps and confidence scores.
   - Runs the constrained generator to turn the glosses into an English sentence and tokens. If generation fails validation, it falls back to a template.
5. **Go response.** Go maps the result to the public response (or to a typed error), deletes the temporary file, and records timings. When history is enabled, it stores the **text result only**.
6. **Browser result.** The browser renders the result. Each token links to the sign it came from, so the typography can time words to the video and emphasise low-confidence words differently.

The request is **synchronous** for the MVP. A clip of 10 s or less should finish well inside the timeouts in API_CONTRACT.md, but this is unmeasured until milestone 9. If it does not, the contract already reserves an asynchronous `202` path.

## Trust boundaries and security

| Boundary | Controls |
| --- | --- |
| Browser → Go | TLS (via Vite in dev). Body size cap, multipart part allowlist, magic-byte sniffing, metadata schema validation, per-client rate limit, Supabase JWT verification on protected routes. CORS is an exact-origin allowlist from env and is not needed in dev. |
| Go → Python | Loopback only, plus a shared `ML_INTERNAL_TOKEN` header so another local process cannot call the service by accident. Go passes the clip it already validated and never forwards client headers. |
| Go → Supabase | The service-role key lives **only** in the Go environment. The browser may hold only the public anon key and the user's own access token. |
| Model weights | Stored under `ml-service/models/` on the laptop and git-ignored. They never go into the web bundle, an APK or the iOS app, and nothing downloads them automatically. |

**Privacy.** Clips of people signing are biometric-adjacent personal data. By default the system does not retain clips. Go deletes the temporary file after each request, Python works in memory or deletes its own temporary files, and logs never contain clip bytes or the full result text. Retention is decision D4.

## Extensibility toward live translation (not built in MVP)

The web frontend separates three concerns, so the transport can change later without rewriting the UI:

- **`CaptureSource`.** The camera lifecycle (start, stop, device switching, permission state). This piece stays as it is for live mode.
- **`ClipRecorder`.** Wraps `MediaRecorder` for the MVP. A later `FrameSampler` (canvas or `VideoFrame` sampling, possibly landmarks on the device) would sit beside it.
- **`TranslationClient`.** `translateClip(blob, metadata)` now. Later, `openSession()` returns a stream of partial results.

On the server side, the ML contract's `RecognitionResult` already uses clip-relative timestamps and ordered segments. A streaming recognizer could emit the same segment type incrementally. WebSockets and frame streaming are explicitly deferred until the clip flow is stable (see INTEGRATION_PLAN.md).

## Proposed repository layout

```text
/                          existing iOS app (unchanged)
  Visualiser/ VisualiserCore/ VisualiserTests/ Visualiser.xcodeproj Scripts/
web/                       React frontend                       (milestone 2)
backend-go/                Go API                               (milestone 3)
ml-service/                Python inference                     (milestone 4)
  models/                  local weights, git-ignored
contracts/                 shared JSON examples + checks used by every team's tests
docs/                      this document and the other team docs
```

## Non-goals for the MVP

- Continuous streaming or WebSockets.
- Downloading or bundling models into any client.
- Claims of NPU or GPU acceleration on Snapdragon before the team measures it.
- Clip storage.
- Production deployment.
- Languages other than the one chosen under D1.
