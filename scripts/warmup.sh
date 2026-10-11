#!/usr/bin/env bash
# Pings every service's /health (and /readyz where it matters) in parallel so cold Render/Neon
# instances are warm before a demo recording or judge review. See
# architecture/deployment-zero-cost.md §4 "Warm-up script".
set -euo pipefail

: "${API_BASE_URL:?set API_BASE_URL to the deployed gateway base URL}"

urls=(
  "$API_BASE_URL/gateway/health"
  "$API_BASE_URL/gateway/readyz"
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
echo "warmup: all services responded"
