#!/usr/bin/env bash
# End-to-end check through the real Go server: upload a generated clip, expect the contract back.
# Run while scripts/run.sh is up. Exit code 0 = pass.
set -euo pipefail
BASE="${1:-http://127.0.0.1:8080}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
ffmpeg -loglevel error -f lavfi -i testsrc=size=640x480:rate=30 -t 2 -c:v libvpx "$TMP/clip.webm"
echo '{"client_request_id":"6f1c8a52-4f0e-4a4e-9a51-3e2b7d1c9a10","recording":{"duration_ms":2000,"mime_type":"video/webm"}}' > "$TMP/meta.json"
code=$(curl -s -o "$TMP/out.json" -w '%{http_code}' -F "metadata=<$TMP/meta.json;type=application/json" -F "clip=@$TMP/clip.webm;type=video/webm" "$BASE/api/v1/translations")
echo "HTTP $code"; cat "$TMP/out.json"; echo
python3 - "$code" "$TMP/out.json" <<'PY'
import json, sys
code, body = int(sys.argv[1]), json.load(open(sys.argv[2]))
if code == 200:
    assert body["sentence"] and isinstance(body["signs"], list), body
elif code in (422, 503):
    # A test pattern has no signer: no_signs_detected is the correct answer from the real model;
    # inference_unavailable means no recognizer is trained yet.
    assert body["error"]["code"] in ("no_signs_detected", "inference_unavailable"), body
else:
    raise SystemExit(f"unexpected status {code}")
print("smoke: OK")
PY
