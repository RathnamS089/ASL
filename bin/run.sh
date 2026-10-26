#!/usr/bin/env bash
# Start the whole stack on this Mac, all on loopback:
#   generator (mlx_lm.server :8002, optional) -> ml-service (:8001) -> backend-go (:8080, serves web/dist)
# Expose it to your devices with bin/expose.sh (Tailscale Serve).
#
#   bin/run.sh            real recognizer + fine-tuned generator if present, else what exists
#   bin/run.sh --mock     mock ML (no models needed), useful for UI work
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
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
ADAPTER="$ML/finetune/adapters/qwen35-2b-gloss-r2"
if [[ $MOCK == 0 && -d "$ML/models/Qwen3.5-2B" ]]; then
  args=(--model "$ML/models/Qwen3.5-2B" --host 127.0.0.1 --port 8002)
  [[ -f "$ADAPTER/adapters.safetensors" ]] && args+=(--adapter-path "$ADAPTER")
  echo "-> generator: Qwen3.5-2B ${ADAPTER:+(+ LoRA r2 if present)} on :8002"
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
