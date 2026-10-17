import { cn } from "@/lib/utils";

interface RailProps {
  steps: readonly string[];
  /** Index of the step the buyer is on. Earlier steps are done. */
  current: number;
  label: string;
  className?: string;
}

/** Square nodes joined by bars: filled Seal when done, outlined when current or ahead. */
export function Rail({ steps, current, label, className }: RailProps) {
  return (
    <ol className={cn("flex items-start", className)} aria-label={label}>
      {steps.map((step, i) => (
        <li
          key={step}
          aria-current={i === current ? "step" : undefined}
          className={cn(
            "flex min-w-0 flex-col gap-1",
            i < steps.length - 1 ? "flex-1" : "flex-none",
          )}
        >
          <div className="flex h-6 items-center">
            <span
              aria-hidden="true"
              className={cn(
                "box-border h-4 w-4 flex-none",
                i < current && "bg-seal",
                i === current && "border-[3px] border-fg bg-panel",
                i > current && "border-[3px] border-line-strong bg-panel",
              )}
            />
            {i < steps.length - 1 && (
              <span
                aria-hidden="true"
                className={cn("h-1 flex-1", i < current ? "bg-seal" : "bg-line")}
              />
            )}
          </div>
          <span className="text-[10px] font-bold uppercase leading-tight tracking-[0.08em] text-mute">
            {step}
          </span>
        </li>
      ))}
    </ol>
  );
}

const FLOW_STEPS = ["Intent", "Cart", "Approve"] as const;

/** Where the buyer is in intent, cart, approve. */
export function FlowRail({ step, className }: { step: 0 | 1 | 2; className?: string }) {
  return <Rail steps={FLOW_STEPS} current={step} label="Buying steps" className={className} />;
}
