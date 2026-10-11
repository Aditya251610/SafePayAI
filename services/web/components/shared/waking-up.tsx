/**
 * Cold-start "waking up" UI (REQ-WB-050, spec.md sec 12).
 *
 * Wave 4 skeleton: static presentational component only. No real timeout/
 * retry wiring - that depends on lib/api-client.ts being wired to the real
 * gateway (Wave 5) and on implementation-tuned initial-timeout / give-up
 * thresholds (spec.md sec 12 explicitly declines to invent those numbers
 * here).
 *
 * TODO Wave 5:
 *   - Trigger this when a BFF call exceeds the initial-timeout threshold
 *     with no response yet.
 *   - Wire automatic retry-with-backoff for idempotent calls only (reads,
 *     or any call carrying an Idempotency-Key).
 *   - After the give-up threshold, swap to the "offline-video banner"
 *     fallback (static explanation + link/thumbnail to the recorded demo
 *     video).
 */
export function WakingUp() {
  return (
    <div role="status" aria-live="polite" className="flex flex-col items-center gap-3 p-8 text-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent motion-reduce:animate-none" />
      <p className="text-sm text-muted-foreground">
        Waking up the demo server - this can take about a minute on a cold start
        (sandbox free-tier hosting).
      </p>
    </div>
  );
}
