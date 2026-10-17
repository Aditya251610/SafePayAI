import { Tag } from "@/components/ui/tag";
import { SANDBOX_NOTICE } from "@/lib/honesty/copy";

/** Persistent disclosure on every page. It has no dismiss control. */
export function SandboxBanner() {
  return (
    <div
      role="note"
      aria-label="Sandbox disclosure"
      className="flex w-full flex-wrap items-center justify-center gap-3 border-b-2 border-dashed border-line-strong bg-panel-2 px-4 py-2 text-center text-xs font-bold uppercase tracking-[0.1em] text-mute"
    >
      <Tag tone="dashed">Sandbox</Tag>
      <span>{SANDBOX_NOTICE}</span>
    </div>
  );
}
