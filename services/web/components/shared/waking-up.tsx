/** Shown while the backend wakes from a cold start (503 UPSTREAM_WAKING). */
export function WakingUp() {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex flex-col items-center gap-3 p-8 text-center"
    >
      <div className="h-8 w-8 animate-spin border-2 border-fg border-t-transparent motion-reduce:animate-none" />
      <p className="max-w-md text-sm text-mute">
        Waking up the demo server. A cold start on free hosting can take about a minute.
      </p>
    </div>
  );
}
