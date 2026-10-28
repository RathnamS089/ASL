#!/usr/bin/env bash
# Start the whole stack on this Mac, all on loopback:
#   generator (mlx_lm.server :8002, optional) -> ml-service (:8001) -> backend-go (:8080, serves web/dist)
# Expose it to your devices with bin/expose.sh (Tailscale Serve).
#
#   bin/run.sh            real recognizer + fine-tuned generator if present, else what exists
#   bin/run.sh --mock     mock ML (no models needed), useful for UI work
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# This Mac is the server for phones elsewhere, so keep it from sleeping while the stack runs.
if [[ -z "${VISUALISER_AWAKE:-}" ]] && command -v caffeinate >/dev/null; then
  VISUALISER_AWAKE=1 exec caffeinate -is "$0" "$@"
fi
MOCK=0
[[ "${1:-}" == "--mock" ]] && MOCK=1

: "${ML_INTERNAL_TOKEN:=$(openssl rand -hex 24)}"   # per-run secret shared by Go and Python
export ML_INTERNAL_TOKEN
pids=()
cleanup() { trap - EXIT INT TERM; kill "${pids[@]}" 2>/dev/null || true; wait 2>/dev/null || true; }
trap cleanup EXIT INT TERM

wait_for() { # url name
  for _ in $(seq 1 120); do curl -fs "$1" >/dev/null 2>&1 && return 0; sleep 1; done
  echo "$2 did not start (check its log above)"; exit 1
}

ML="$ROOT/ml-service"
GEN_ENV=(GEN_BACKEND=template)
# Generator choice (see ml-service/MODEL_SELECTION.md): Qwen3.5-4B 4-bit was the most accurate
# and fastest on recognizer-vocabulary glosses; the fine-tuned 2B is the fallback.
# Override with GEN_MODEL_DIR=... [GEN_ADAPTER_DIR=...] bin/run.sh
if [[ -z "${GEN_MODEL_DIR:-}" ]]; then
  if [[ -d "$ML/models/Qwen3.5-4B-4bit" ]]; then GEN_MODEL_DIR="$ML/models/Qwen3.5-4B-4bit"
  elif [[ -d "$ML/models/Qwen3.5-2B" ]]; then
    GEN_MODEL_DIR="$ML/models/Qwen3.5-2B"
    [[ -f "$ML/finetune/adapters/qwen35-2b-gloss-r2/adapters.safetensors" ]] && GEN_ADAPTER_DIR="${GEN_ADAPTER_DIR:-$ML/finetune/adapters/qwen35-2b-gloss-r2}"
  fi
fi
if [[ $MOCK == 0 && -n "${GEN_MODEL_DIR:-}" ]]; then
  args=(--model "$GEN_MODEL_DIR" --host 127.0.0.1 --port 8002)
  [[ -n "${GEN_ADAPTER_DIR:-}" ]] && args+=(--adapter-path "$GEN_ADAPTER_DIR")
  echo "-> generator: $(basename "$GEN_MODEL_DIR")${GEN_ADAPTER_DIR:+ + $(basename "$GEN_ADAPTER_DIR")} on :8002"
  "$ML/.venv/bin/mlx_lm.server" "${args[@]}" 2>&1 | sed 's/^/[gen] /' &
  pids+=($!)
  wait_for http://127.0.0.1:8002/v1/models generator
  GEN_ENV=(GEN_BACKEND=openai_compat GEN_BASE_URL=http://127.0.0.1:8002/v1 GEN_MODEL=default_model)
fi

echo "-> ml-service on :8001 (mock=$MOCK)"
(cd "$ML" && env ML_MOCK=$MOCK ML_MOCK_DELAY_MS=800 "${GEN_ENV[@]}" \
  .venv/bin/uvicorn visualiser_ml.app:create_app --factory --host 127.0.0.1 --port 8001 --log-level warning) 2>&1 \
  | grep --line-buffered -v -E '^(I0000|W0000|INFO: Created TensorFlow)' | sed 's/^/[ml] /' &
pids+=($!)
wait_for http://127.0.0.1:8001/health ml-service
curl -s http://127.0.0.1:8001/health | sed 's/^/[ml] health: /'; echo

if [[ ! -f "$ROOT/web/dist/index.html" ]]; then
  echo "-> building web app"; (cd "$ROOT/web" && npm run build >/dev/null)
fi
echo "-> backend-go on :8080"
(cd "$ROOT/backend-go" && go build -o "$ROOT/backend-go/bin/visualiser-api" ./cmd/server)
(cd "$ROOT/backend-go" && API_LISTEN_ADDR=127.0.0.1:8080 "$ROOT/backend-go/bin/visualiser-api") 2>&1 | sed 's/^/[api] /' &
pids+=($!)
wait_for http://127.0.0.1:8080/health api

echo
echo "VISUALISER is running at http://127.0.0.1:8080 (this Mac only)."
echo "For your phone: bin/expose.sh   then open the https://….ts.net address it prints."
wait
