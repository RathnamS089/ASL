#!/usr/bin/env bash
# Expose the Go server (127.0.0.1:8080) to devices on YOUR tailnet only, over HTTPS.
# Phones need the Tailscale app, signed in to the same account. Never uses Funnel (public).
#   scripts/expose.sh          start serving
#   scripts/expose.sh off      stop serving
set -euo pipefail
TS="$(command -v tailscale || echo /Applications/Tailscale.app/Contents/MacOS/Tailscale)"
if [[ ! -x "$TS" ]]; then
  echo "Tailscale is not installed. Install it (brew install --cask tailscale), open it and sign in." >&2; exit 1
fi
if [[ "${1:-}" == "off" ]]; then "$TS" serve reset; echo "Stopped serving."; exit 0; fi
"$TS" status >/dev/null 2>&1 || { echo "Tailscale is not connected. Open the Tailscale app and sign in." >&2; exit 1; }
"$TS" serve --bg 8080
"$TS" serve status
echo
echo "Open the https://…ts.net address above on a phone signed in to your tailnet."
