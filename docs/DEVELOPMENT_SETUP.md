# Development setup (LAN, phones, HTTPS)

Status: **proposal**. The `web/`, `backend-go/` and `ml-service/` commands below become real as each milestone lands. Each owner updates their section when their scaffold is merged.

## Ports and processes

| Process | Bind | Port | Firewall rule | Reached by |
| --- | --- | --- | --- | --- |
| Vite dev server (HTTPS) | `0.0.0.0` | 5173 | **yes**, Private profile only | phones and laptops on the Wi-Fi |
| Go API | `127.0.0.1` (`API_LISTEN_ADDR`) | 8080 | no, unless the iOS app needs direct access | Vite proxy |
| Python ML service | `127.0.0.1` | 8001 | **never** | Go only |

## Configuration, never hard-coded IPs

The laptop's LAN IP changes between networks, so it must not appear in source. Each component reads a git-ignored `.env` file, and a committed `.env.example` lists every key with a safe default.

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

## Why phones need HTTPS

`navigator.mediaDevices.getUserMedia` exists only in a **secure context**:

- `http://localhost` and `http://127.0.0.1` count as secure, so on the laptop itself plain `npm run dev` works.
- `http://192.168.x.y:5173` opened on a phone is **not** secure. `navigator.mediaDevices` is `undefined`, and no permission prompt ever appears. The web app should detect this (`window.isSecureContext === false`) and show a clear message rather than a generic error.

### Recommended: mkcert (a local CA trusted by each test device)

1. On the laptop, install [mkcert](https://github.com/FiloSottile/mkcert). On Windows, `winget install FiloSottile.mkcert` or `choco install mkcert` are options; check that the package is the ARM64 build or that it runs under emulation.
2. Create the local CA with `mkcert -install`.
3. Create a certificate for the names phones will use. Include the current LAN IP; look it up with `ipconfig` under the Wi-Fi adapter.

   ```powershell
   mkdir .certs
   mkcert -cert-file .certs/dev-cert.pem -key-file .certs/dev-key.pem localhost 127.0.0.1 ::1 <LAN-IP> <laptop-hostname>.local
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

## Windows Firewall (Snapdragon laptop)

Run these in an **elevated PowerShell**.

1. Make sure the Wi-Fi network is classified as *Private*. Public networks block inbound connections.

   ```powershell
   Get-NetConnectionProfile
   Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private
   ```

2. Allow only the Vite port, only on Private networks:

   ```powershell
   New-NetFirewallRule -DisplayName "VISUALISER Vite dev (5173)" -Direction Inbound -Protocol TCP -LocalPort 5173 -Action Allow -Profile Private
   ```

3. Only if a native client must reach Go directly (and Go is then bound to the LAN with TLS):

   ```powershell
   New-NetFirewallRule -DisplayName "VISUALISER Go API (8080)" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow -Profile Private
   ```

4. Remove the rules when you are done:

   ```powershell
   Remove-NetFirewallRule -DisplayName "VISUALISER Vite dev (5173)"
   ```

When Node first listens, Windows may also show an "allow access" prompt. Allow it on **Private networks only**. Create no rule for port 8001.

## Network checklist

- The phone and the laptop are on the **same SSID**, not a guest network. Many campus, office and guest networks enable **client isolation**, which blocks device-to-device traffic. A phone hotspot or a home router avoids that.
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

## Python on Windows on ARM

- Decide between native ARM64 Python and x64 Python under emulation per dependency (see [ML_CONTRACT.md](ML_CONTRACT.md#windows-on-arm-notes-to-verify-not-assumptions)). Record the interpreter (`python -c "import platform; print(platform.machine())"`) and the lockfile in `ml-service/README.md`.
- Use a virtual environment inside `ml-service/` (`.venv/`, git-ignored).
- Put weights in `ml-service/models/` by hand. Nothing downloads them automatically, and they are never committed.

## Shared checks available today

From the repository root:

```bash
python3 contracts/check_examples.py
```

```bash
swiftc -parse-as-library VisualiserCore/Sources/VisualiserCore/Translation.swift Scripts/VerifyContractCompat.swift -o /tmp/visualiser-contract-compat && /tmp/visualiser-contract-compat
```

The first validates the shared JSON examples against the contract invariants. The second confirms that the v1 response example still decodes with the existing iOS `TranslationResponse`. Run the Swift check from the repository root.
