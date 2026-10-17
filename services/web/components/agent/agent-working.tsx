"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import { Slab } from "@/components/ui/slab";
import { Tag } from "@/components/ui/tag";

/** The agent gives up after this long and the buyer chooses what to do. */
export const WATCHDOG_SECONDS = 20;

/** Seconds since `active` became true, ticking once a second. */
export function useElapsed(active: boolean): number {
  const [s, setS] = React.useState(0);
  React.useEffect(() => {
    if (!active) {
      setS(0);
      return;
    }
    const started = Date.now();
    const id = setInterval(() => setS(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(id);
  }, [active]);
  return s;
}

/** The only looping state. It stops being a spinner after 20 seconds. */
export function AgentWorking({
  seconds,
  label = "Reading intent. Checking scope. Drafting cart. Decides nothing.",
  onRetry,
}: {
  seconds: number;
  label?: string;
  onRetry?: () => void;
}) {
  const slow = seconds >= WATCHDOG_SECONDS;
  return (
    <Slab raised notched className="flex flex-col gap-3" role="status" aria-live="polite">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Tag tone="seal">Agent working</Tag>
        <span className="tabular text-xs text-dim">Elapsed {seconds} s</span>
      </div>
      {!slow && (
        <div aria-hidden="true" className="h-2 w-full overflow-hidden border border-line-strong">
          <div className="h-full w-1/4 animate-[agent-bar_1.2s_steps(4)_infinite] bg-seal motion-reduce:animate-none" />
        </div>
      )}
      <p className="text-sm text-mute">
        {slow ? "Taking longer than expected. You can wait, or try again." : label}
      </p>
      {slow && onRetry && (
        <Button size="sm" variant="secondary" className="self-start" onClick={onRetry}>
          Try again
        </Button>
      )}
    </Slab>
  );
}
