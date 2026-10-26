# backend-go

The VISUALISER API in Go, standard library only. It implements [docs/API_CONTRACT.md](../docs/API_CONTRACT.md), calls the Python service per [docs/ML_CONTRACT.md](../docs/ML_CONTRACT.md), and serves the built web app. One loopback port carries everything, and Tailscale Serve exposes that port to your phones.

```text
cmd/server/            main: config, HTTP server timeouts, graceful shutdown
internal/config/       environment settings (see .env.example)
internal/api/          routes, upload validation, error envelope, middleware, web app
internal/inference/    ML client (streams the clip) and the bounded inference queue
```

| Route | Purpose |
| --- | --- |
| `GET /health`, `/api/health` | Liveness |
| `GET /health/ready`, `/api/health/ready` | Is the ML service ready (or mock mode)? |
| `POST /v1/translations`, `/api/v1/translations` | Multipart `metadata` + `clip`, or a raw video body (iOS compatibility) |
| `GET /*` | The web app from `WEB_DIST_DIR`, with SPA fallback |

What it enforces:
- **Uploads.** Body cap, exact multipart parts, magic-byte container check (WebM or MP4/MOV), 4 KiB metadata, sign language, and the clip duration the client reports.
- **Load.** One inference at a time with a short queue (`503 busy`), plus a per-user rate limit (`429`). Behind Tailscale Serve, the limit is keyed on your Tailscale login.
- **Timeouts.** 30 s to read the upload, 45 s for the ML call (`504`), 100 s to write the response.
- **Headers.** Security headers on every response: CSP, `Permissions-Policy: camera=(self)`, no framing.
- **Privacy.** The clip is spooled to a temp file and always deleted. Logs never contain clip bytes or result text.

## Run

From `backend-go/`. To test without the ML service, add `MOCK_TRANSLATION=1`.

```bash
set -a; source .env; set +a; go run ./cmd/server
```

```bash
go test -race ./...
```
