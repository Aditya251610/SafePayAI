import { CASE_RAIL_STEPS, railStep } from "@/lib/format/case-rail";
import { cn } from "@/lib/utils";

/** Five-stage case rail. `state` is the backend case state. */
export function CaseRail({ state, className }: { state: string; className?: string }) {
  const current = railStep(state);
  return (
    <ol className={cn("flex flex-wrap gap-2", className)} aria-label="Case progress">
      {CASE_RAIL_STEPS.map((label, i) => (
        <li
          key={label}
          aria-current={i === current ? "step" : undefined}
          className={cn(
            "inline-flex h-7 items-center border-2 px-2.5 text-[11px] font-bold uppercase tracking-[0.08em]",
            i === current && "border-fg text-fg",
            i < current && "border-line-strong bg-panel-2 text-mute",
            i > current && "border-dashed border-line-strong text-dim",
          )}
        >
          {label}
        </li>
      ))}
    </ol>
  );
}
