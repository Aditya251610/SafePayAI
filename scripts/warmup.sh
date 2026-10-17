#!/usr/bin/env bash
# Pings every service's health route (in parallel) across all 4 Profile B Render hosts, so
# cold Render/Neon instances are warm before a demo recording or judge review. See
# architecture/deployment-zero-cost.md §4 "Warm-up script" and deploy/profile-b/render.yaml
# for the host/mount topology these URLs mirror.
#
# Previously this only pinged the gateway host's /gateway/health - wrong route (the real one
# is /healthz, not /health - render.yaml hit and fixed this same mismatch) and only one of the
# 4 hosts, so the other 3 (which sleep independently on Render's free tier) never actually got
# warmed, defeating the point of running this before a demo.
set -euo pipefail

EDGE_BASE_URL="${EDGE_BASE_URL:-https://safepayai-edge.onrender.com}"
CORE_BASE_URL="${CORE_BASE_URL:-https://safepayai-core.onrender.com}"
AI_BASE_URL="${AI_BASE_URL:-https://safepayai-ai.onrender.com}"
PAYPAL_BASE_URL="${PAYPAL_BASE_URL:-https://safepayai-paypal.onrender.com}"

urls=(
  "$EDGE_BASE_URL/gateway/healthz"
  "$EDGE_BASE_URL/gateway/readyz"
  "$CORE_BASE_URL/mandate/healthz"
  "$CORE_BASE_URL/catalog/healthz"
  "$CORE_BASE_URL/checkout/healthz"
  "$CORE_BASE_URL/tracking/healthz"
  "$CORE_BASE_URL/resolution/healthz"
  "$CORE_BASE_URL/audit/healthz"
  "$AI_BASE_URL/shopping-agent/healthz"
  "$AI_BASE_URL/triage-ai/healthz"
  "$PAYPAL_BASE_URL/paypal-adapter/health"
)

pids=()
for url in "${urls[@]}"; do
  curl --silent --show-error --retry 5 --retry-delay 3 --max-time 90 "$url" &
  pids+=($!)
done

fail=0
for pid in "${pids[@]}"; do
  wait "$pid" || fail=1
done

if [ "$fail" -ne 0 ]; then
  echo "warmup: one or more health checks failed" >&2
  exit 1
fi
echo "warmup: all $((${#urls[@]})) service health routes responded across all 4 hosts"
