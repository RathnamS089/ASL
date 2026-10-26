# VISUALISER architecture

VISUALISER turns a short sign-language clip into English text and plays the text back as kinetic typography. Everything runs on one **Apple M4 Mac mini (16 GB)**. That Mac has no camera, so **phones are the cameras**: they open the web app over a private HTTPS address from Tailscale.

```text
 Phone (camera)                          Mac mini M4 — everything on 127.0.0.1
┌───────────────────────┐  HTTPS (tailnet  ┌──────────────────────────────────────────────────────────┐
│ Safari / Chrome       │  only, real cert)│ tailscale serve ─▶ backend-go :8080                       │
│  web app (React)      │─────────────────▶│                     ├─ /            web/dist (the app)    │
│  camera → 10 s clip   │  https://<mac>   │                     └─ /api/v1/...  validate, queue, map  │
│  kinetic result       │  .ts.net         │                          │ multipart + X-Internal-Token   │
└───────────────────────┘                  │                          ▼                                │
                                           │                    ml-service :8001 (FastAPI)              │
                                           │   decode (OpenCV) → landmarks (MediaPipe Holistic:        │
                                           │   hands, pose, face) → segment → classify (MLX            │
                                           │   transformer, ISLR-trained) → glosses                    │
                                           │                          │ glosses                        │
                                           │                          ▼                                │
                                           │   generator: mlx_lm.server :8002 — Qwen3.5-2B + LoRA r2   │
                                           │   (constraint check; template fallback)                   │
                                           └──────────────────────────────────────────────────────────┘
```

| Component | Code | Listens on | Reachable from |
| --- | --- | --- | --- |
| Web app | `web/` (React 19, TypeScript, Vite 8, Tailwind 4, Motion) | served by Go | your tailnet devices |
| API | `backend-go/` (Go, standard library only) | `127.0.0.1:8080` | Tailscale Serve |
| ML service | `ml-service/` (FastAPI) | `127.0.0.1:8001` | Go only (internal token) |
| Generator | `mlx_lm.server`, Qwen3.5-2B + LoRA adapter | `127.0.0.1:8002` | ML service only |
| Exposure | Tailscale Serve (`bin/expose.sh`) | `https://<mac>.<tailnet>.ts.net` | devices signed in to your tailnet |

Run the whole stack with `bin/run.sh` (add `--mock` to skip the models). Expose it with `bin/expose.sh`.

## Why Tailscale Serve

- **A real HTTPS certificate.** Phones only allow the camera on secure pages, and a `*.ts.net` address passes that check with no certificate setup on the phones.
- **Private by default.** Only devices signed in to your Tailscale account can connect. Nothing is published on the internet (Funnel is never used), and clips never pass through a third-party relay in readable form.
- **One port.** Go serves both the app and the API, so the page and its API share an origin. There is no CORS to configure.
- **Works from any network.** The phone doesn't need to be on the Mac's Wi-Fi.

The LAN-only alternative (mkcert on the same Wi-Fi) is still documented in [DEVELOPMENT_SETUP.md](DEVELOPMENT_SETUP.md).

## Request flow

1. **Phone.** `getUserMedia` (video only, 640×480 ideal) shows a preview. After a 3-2-1 countdown, `MediaRecorder` records up to 10 s: MP4 on Safari, WebM on Chrome.
2. **Upload.** `POST /api/v1/translations` sends multipart `metadata` + `clip` ([API_CONTRACT.md](API_CONTRACT.md)).
3. **Go checks the upload:**
   - caps the body at 20 MiB
   - accepts exactly the `metadata` and `clip` parts
   - checks the container from its first bytes (WebM or MP4/MOV)
   - validates the metadata, the sign language and the client-reported duration
   - applies a per-user rate limit, keyed on the Tailscale login when it is present
4. **Go queues and forwards.** It waits for the single inference slot (`503 busy` when the queue is full), then streams the clip to Python with a 45 s deadline ([ML_CONTRACT.md](ML_CONTRACT.md)).
5. **Python recognizes:**
   - decodes the clip with OpenCV and samples it at 15 fps
   - runs MediaPipe HolisticLandmarker for 543 landmarks per frame (face, hands, pose), in the same layout as the Google ISLR training data
   - splits the clip into signs at hands-down gaps and pauses in motion
   - classifies each segment with the MLX transformer, keeping signs above the confidence floor
6. **Python generates.** Glosses go to the generator: Qwen3.5-2B with the round-2 LoRA adapter, with thinking off. The output must pass the constraint check, or the literal template is used.
7. **Go answers.** It maps the result to the public response (no signs → `422 no_signs_detected`) and deletes the temporary clip.
8. **Phone.** The words animate in time with the signs they came from. Low-confidence words are faded and underlined.

## The recognizer

| Piece | File | Notes |
| --- | --- | --- |
| Landmarks | `ml-service/visualiser_ml/recognition/landmarks.py` | MediaPipe 1.1.1 `HolisticLandmarker` (model `holistic_landmarker.task`, 13.7 MB, pinned v1), ISLR landmark order |
| Features | `recognition/features.py` | **Shared by training and serving.** Dominant hand first, with left-handed signing mirrored. Uses 21+21 hand points, 7 pose points, and 56 face points (lips, brows, eye corners, nose). Centred on the shoulders and scaled by shoulder width, then resampled to 32 frames with velocities and hand-presence flags added. |
| Segmenter | `recognition/segmenter.py` | Bridges hand-tracking gaps under 0.25 s, drops flicker under 0.3 s, and splits runs over 2.4 s at motion minima. **Untuned:** measure it on real phone clips. |
| Classifier | `recognition/model.py` | 3-layer transformer (dim 192), MLX on the M4 GPU |
| Training | `ml-service/training/islr/` | Google ISLR (Kaggle `asl-signs`, CC-BY 4.0): 250 isolated ASL signs, signer-held-out split |

**"Face" means expression, not identity.** Facial movement carries grammar in sign languages, so face landmarks are model input. Nothing identifies, stores or matches who is signing.

## Trust boundaries

| Boundary | Controls |
| --- | --- |
| Phone → Go | Tailscale (only your devices) plus HTTPS. Upload validation, rate limit, queue, and security headers (CSP, `Permissions-Policy: camera=(self)`, no framing). |
| Go → Python | Loopback only. A per-run random `ML_INTERNAL_TOKEN` (made by `bin/run.sh`), compared in constant time. |
| Python → generator | Loopback only. The output is never trusted: it is parsed, constraint-checked, and falls back to the template. |
| Data | Clips are temporary files, deleted after every request. Logs hold no clip bytes or result text. Weights and datasets stay on the Mac (git-ignored). |

Auth and history (Supabase, milestone 7) are not built. With Tailscale, only your own devices can reach the app. Add accounts if you ever open it wider.

## Repository layout

```text
web/            React app (served by Go from web/dist)
backend-go/     Go API + static serving
ml-service/     recognizer, generator, fine-tuning, benchmarks, ISLR training
contracts/      shared JSON examples + checks used by every component's tests
bin/            run.sh (whole stack), expose.sh (Tailscale Serve), smoke.sh (end-to-end check)
Scripts/        Swift verification scripts for the iOS client
docs/           this file, contracts, setup, datasets, plan
Visualiser*/    the earlier native iOS client (see README)
```
