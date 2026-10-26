# Development setup (LAN, phones, HTTPS)

Status: **proposal**. The `web/`, `backend-go/` and `ml-service/` commands below become real as each milestone lands. Each owner updates their section when their scaffold is merged.

## Ports and processes

| Process | Bind | Port | Firewall rule | Reached by |
| --- | --- | --- | --- | --- |
| Vite dev server (HTTPS) | `0.0.0.0` | 5173 | allow `node` if the macOS firewall is on | phones and laptops on the Wi-Fi |
| Go API | `127.0.0.1` (`API_LISTEN_ADDR`) | 8080 | no, unless the iOS app needs direct access | Vite proxy |
| Python ML service | `127.0.0.1` | 8001 | **never** | Go only |
| Generator server (`mlx_lm.server`) | `127.0.0.1` | 8002 | **never** | ML service only |

## Configuration, never hard-coded IPs

The Mac's LAN IP changes between networks, so it must not appear in source. Each component reads a git-ignored `.env` file, and a committed `.env.example` lists every key with a safe default.

`web/.env.local`:

```dotenv
VITE_API_BASE_URL=/api                  # relative: same origin as the page
DEV_API_PROXY_TARGET=http://127.0.0.1:8080
DEV_HTTPS_CERT=../.certs/dev-cert.pem   # created per machine by mkcert, git-ignored
DEV_HTTPS_KEY=../.certs/dev-key.pem
# Milestone 7 only. The anon key is public by design; NEVER put the service-role key here.
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
```

Only `VITE_*` variables reach the browser bundle. The `DEV_*` variables are read by `vite.config.ts` in Node and never shipped.

`backend-go/.env`:

```dotenv
API_LISTEN_ADDR=127.0.0.1:8080
ML_BASE_URL=http://127.0.0.1:8001
ML_INTERNAL_TOKEN=change-me-locally
CORS_ALLOWED_ORIGINS=                   # empty in dev: Vite proxy makes requests same-origin
MAX_UPLOAD_BYTES=20971520
INFERENCE_CONCURRENCY=1
INFERENCE_QUEUE_DEPTH=4
MOCK_TRANSLATION=1                      # milestone 3: return the shared example without calling ML
SUPABASE_URL=
SUPABASE_JWT_AUDIENCE=authenticated
SUPABASE_SERVICE_ROLE_KEY=              # server only
```

`ml-service/.env`:

```dotenv
ML_LISTEN_HOST=127.0.0.1
ML_LISTEN_PORT=8001
ML_INTERNAL_TOKEN=change-me-locally     # must match Go
ML_MODEL_DIR=./models
ML_MOCK=1
ML_MOCK_DELAY_MS=1500
ML_LOW_CONFIDENCE_THRESHOLD=            # set from validation data at M9
```

Proposed `vite.config.ts` dev server (the web owner adapts it at M2/M3):

```ts
import fs from "node:fs";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const https = env.DEV_HTTPS_CERT && env.DEV_HTTPS_KEY
    ? { cert: fs.readFileSync(env.DEV_HTTPS_CERT), key: fs.readFileSync(env.DEV_HTTPS_KEY) }
    : undefined;
  return {
    plugins: [react()],
    server: {
      host: true,          // listen on all interfaces so phones can connect
      port: 5173,
      strictPort: true,
      https,
      proxy: {
        "/api": {
          target: env.DEV_API_PROXY_TARGET || "http://127.0.0.1:8080",
          rewrite: (p) => p.replace(/^\/api/, ""),
        },
      },
    },
  };
});
```

## Quick start (recommended): one Mac, phones over Tailscale

The Mac mini has no camera, so you sign to a phone that opens the app on the Mac.

1. **Install the toolchain on the Mac:**

   ```bash
   brew install go node ffmpeg
   ```

   ```bash
   cd ml-service && python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev,recognition,llm]'
   ```

   ```bash
   cd web && npm install && npm run build
   ```

2. **Models** (downloaded by hand and git-ignored; see [ml-service/MODEL_SELECTION.md](../ml-service/MODEL_SELECTION.md) and [ml-service/training/islr/README.md](../ml-service/training/islr/README.md)):
   - `ml-service/models/mediapipe/holistic_landmarker.task` (13.7 MB)
   - `ml-service/models/Qwen3.5-2B` (4.55 GB), plus the LoRA adapter from `finetune/`
   - `ml-service/models/recognizer/islr`, produced by training on ISLR

3. **Start everything:**

   ```bash
   scripts/run.sh
   ```

   It works without models too: `scripts/run.sh --mock`.

4. **Tailscale.** Install Tailscale on the Mac (`brew install --cask tailscale`, then open it and sign in) and on each phone (App Store or Play Store, same account). Then expose the app:

   ```bash
   scripts/expose.sh
   ```

   The first time, Tailscale may ask you to enable HTTPS certificates for your tailnet; follow its link. Open the `https://<mac>.<tailnet>.ts.net` address it prints on the phone. To stop exposing it, run `scripts/expose.sh off`.

5. **Check it end to end:**

   ```bash
   scripts/smoke.sh
   ```

Nothing extra needs opening in the macOS firewall: Tailscale carries the traffic, and every server listens on `127.0.0.1` only.

## LAN-only alternative (same Wi-Fi, mkcert)

Use this only if you can't use Tailscale. The rest of this document covers it.

## Why phones need HTTPS

`navigator.mediaDevices.getUserMedia` exists only in a **secure context**:

- `http://localhost` and `http://127.0.0.1` count as secure, so on the Mac itself plain `npm run dev` works.
- `http://192.168.x.y:5173` opened on a phone is **not** secure. `navigator.mediaDevices` is `undefined`, and no permission prompt ever appears. The web app should detect this (`window.isSecureContext === false`) and show a clear message rather than a generic error.

### Recommended: mkcert (a local CA trusted by each test device)

1. On the Mac, install [mkcert](https://github.com/FiloSottile/mkcert) with `brew install mkcert` (add `brew install nss` if you test in Firefox).
2. Create the local CA with `mkcert -install`.
3. Create a certificate for the names phones will use. Include the current LAN IP (`ipconfig getifaddr en0` prints the Wi-Fi address) and the Mac's Bonjour name (`scutil --get LocalHostName`, then add `.local`).

   ```bash
   mkdir -p .certs && mkcert -cert-file .certs/dev-cert.pem -key-file .certs/dev-key.pem localhost 127.0.0.1 ::1 <LAN-IP> <LocalHostName>.local
   ```

   Reissue it when the LAN IP changes. The IP appears only in this command and in the URL typed on the phone, never in source.
4. Install the CA on each phone. `mkcert -CAROOT` prints the folder that holds `rootCA.pem`. Copy **only `rootCA.pem`, never `rootCA-key.pem`**.
   - **iOS / iPadOS.** AirDrop or email the file, then install the profile under *Settings → General → VPN & Device Management*. Then enable it under *Settings → General → About → Certificate Trust Settings*. Both steps are required.
   - **Android.** *Settings → Security → Encryption & credentials → Install a certificate → CA certificate* (menu names vary by vendor). Chrome trusts user-installed CAs for websites.
5. Open `https://<LAN-IP>:5173` on the phone.

Remove the CA from phones when the project ends. Anyone holding `rootCA-key.pem` could impersonate websites to those devices, so keep it out of git and off shared drives.

### Alternatives (with their costs)

| Option | Works for camera? | Cost |
| --- | --- | --- |
| Self-signed cert (for example `@vitejs/plugin-basic-ssl`) and clicking through the warning | Varies by browser. Test on each target phone before relying on it. | Warning on every visit; some browsers restrict a page after a certificate error |
| Android Chrome `chrome://flags/#unsafely-treat-insecure-origin-as-secure` with `http://<LAN-IP>:5173` | Yes, on Android Chrome only | Per-device flag, no iOS equivalent, and easy to forget it is enabled |
| Public tunnel (ngrok, Cloudflare Tunnel) | Yes (real certificate) | **Sends video of signers through a third party.** Avoid it unless the team explicitly accepts that. |

## macOS firewall (M4 Mac)

The macOS firewall works per app, not per port, and it is off by default. Check it under *System Settings → Network → Firewall*, or:

```bash
/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
```

- **Firewall off.** Phones can reach Vite on port 5173 with no extra steps. Go (8080), ML (8001) and MLX (8002) stay unreachable anyway, because they bind to `127.0.0.1`.
- **Firewall on.** The first time Vite listens, macOS asks whether `node` may accept incoming connections. Click **Allow**. Make sure *Block all incoming connections* is off. To allow it ahead of time (asks for your password):

  ```bash
  sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add "$(which node)" && sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp "$(which node)"
  ```

- **Never** allow Python or the MLX server through the firewall. They have no reason to accept LAN traffic.
- If macOS asks whether your terminal app may find devices on the local network, allow it while you develop.

## Network checklist

- The phone and the Mac are on the **same SSID**, not a guest network. Many campus, office and guest networks enable **client isolation**, which blocks device-to-device traffic. A phone hotspot or a home router avoids that.
- **Connectivity test.** From the phone, `https://<LAN-IP>:5173` loads. If it times out, suspect the firewall or client isolation. If it shows a certificate error, the CA is not trusted on the phone.
- **Proxy test.** `https://<LAN-IP>:5173/api/health` returns `{"status":"ok",...}`, which proves the Vite → Go proxy works.

## Camera permission behaviour to test (M8)

| Situation | Expected UI |
| --- | --- |
| Insecure context | "Open this site over HTTPS" message; no camera button |
| First visit | Explain why the camera is needed, then call `getUserMedia` on a user tap |
| `NotAllowedError` (denied) | Steps to re-enable for that browser (iOS: *Settings → Safari → Camera*, or the address-bar "aA" menu; Android Chrome: lock icon → Permissions) |
| `NotReadableError` | "Camera is in use by another app" |
| `NotFoundError` / `OverconstrainedError` | Fall back to looser constraints, then a "no camera found" message |
| Tab hidden or navigated away | Tracks stopped; camera indicator turns off |

iOS Safari requires the `playsinline` and `muted` attributes on the preview `<video>`. The MIME type `MediaRecorder` produces differs by browser, so always negotiate with `MediaRecorder.isTypeSupported`.

## Python and models on the M4 Mac

- Use Python 3.12 (arm64) in a virtual environment inside `ml-service/` (`.venv/`, git-ignored).
- Put weights in `ml-service/models/`. They are downloaded by hand, only after the licence is checked, and never committed. Watch disk space: Qwen3.5-2B alone takes 4.55 GB.
- 16 GB of unified memory is shared by everything. Stop `mlx_lm.server` when you are not using it (Ctrl-C), and check Activity Monitor before adding a second model.

## Shared checks available today

From the repository root:

```bash
python3 contracts/check_examples.py
```

```bash
swiftc -parse-as-library VisualiserCore/Sources/VisualiserCore/Translation.swift Scripts/VerifyContractCompat.swift -o /tmp/visualiser-contract-compat && /tmp/visualiser-contract-compat
```

The first validates the shared JSON examples against the contract invariants. The second confirms that the v1 response example still decodes with the existing iOS `TranslationResponse`. Run the Swift check from the repository root.
