import { CASE_RAIL_STEPS, railStep } from "@/lib/format/case-rail";

import { Rail } from "./rail";

/** Five-stage case rail. `state` is the backend case state. */
export function CaseRail({ state, className }: { state: string; className?: string }) {
  return (
    <Rail
      steps={CASE_RAIL_STEPS}
      current={railStep(state)}
      label="Case progress"
      className={className}
    />
  );
}
