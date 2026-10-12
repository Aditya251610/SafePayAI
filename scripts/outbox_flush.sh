#!/usr/bin/env bash
# Calls POST /internal/outbox/flush on every producer service (S2-06, sprint-plan). These
# endpoints are never routed by the gateway (404 externally per each router's own
# docstring), so this hits each service's own base URL directly, not the gateway.
#
# Each service's flush endpoint is guarded by its own shared cron secret (bare
# INTERNAL_TICK_SECRET convention, or PS_PAYPALADAPTER_OUTBOX_FLUSH_SECRET for
# paypal-adapter, which already had a dedicated field for this). A service whose base URL
# or secret isn't configured (empty var/secret) is skipped, not failed -- lets this run
# safely before every service is deployed, per deployment-zero-cost.md's staged rollout.
#
# Any individual service failure is logged and does not stop the others (events are
# retained in that service's own outbox table either way -- ADR-003 at-least-once).
set -uo pipefail

flush_one() {
  local name="$1" base_url="$2" secret="$3"
  if [ -z "$base_url" ] || [ -z "$secret" ]; then
    echo "outbox_flush: skipping $name (base URL or secret not configured)"
    return 0
  fi
  local out
  out=$(curl --silent --show-error --fail --max-time 30 \
    -X POST "$base_url/internal/outbox/flush" \
    -H "X-Tick-Secret: $secret" 2>&1)
  local status=$?
  if [ "$status" -ne 0 ]; then
    echo "outbox_flush: $name FAILED: $out" >&2
    return 1
  fi
  echo "outbox_flush: $name OK: $out"
  return 0
}

fail=0
flush_one "mandate"        "${PS_MANDATE_BASE_URL:-}"       "${PS_MANDATE_INTERNAL_TICK_SECRET:-}"       || fail=1
flush_one "checkout"       "${PS_CHECKOUT_BASE_URL:-}"      "${PS_CHECKOUT_INTERNAL_TICK_SECRET:-}"       || fail=1
flush_one "shopping-agent" "${PS_SHOPPINGAGENT_BASE_URL:-}" "${PS_SHOPPINGAGENT_INTERNAL_TICK_SECRET:-}"  || fail=1
flush_one "paypal-adapter" "${PS_PAYPALADAPTER_BASE_URL:-}" "${PS_PAYPALADAPTER_OUTBOX_FLUSH_SECRET:-}"   || fail=1
flush_one "tracking"       "${PS_TRACKING_BASE_URL:-}"      "${PS_TRACKING_INTERNAL_TICK_SECRET:-}"       || fail=1
flush_one "resolution"     "${PS_RESOLUTION_BASE_URL:-}"    "${PS_RESOLUTION_TICK_SECRET:-}"              || fail=1
flush_one "triage-ai"      "${PS_TRIAGEAI_BASE_URL:-}"      "${PS_TRIAGEAI_INTERNAL_TICK_SECRET:-}"       || fail=1

exit "$fail"
