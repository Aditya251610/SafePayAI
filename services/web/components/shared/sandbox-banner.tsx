// Persistent, non-dismissible SANDBOX banner (REQ-WB-002). Rendered in the
// root layout so it appears on every page, including error/404 pages.
// Text is exact per spec.md sec 5 - do not paraphrase.
export function SandboxBanner() {
  return (
    <div
      role="note"
      aria-label="Sandbox disclosure"
      className="w-full bg-amber-500 px-4 py-2 text-center text-sm font-medium text-amber-950"
    >
      Sandbox only. No real money. Seeded catalog. Simulated carrier.
    </div>
  );
}
