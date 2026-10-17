import * as React from "react";

import { cn } from "@/lib/utils";

interface SlabProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Hard offset shadow for the one panel that needs the eye. Flare marks money at risk. */
  raised?: boolean | "seal" | "flare";
  /** Angled top-right corner. */
  notched?: boolean;
}

/** The panel surface: a 2 px line border on the panel colour. */
export function Slab({ className, raised, notched, ...props }: SlabProps) {
  const flare = raised === "flare";
  const panel = (
    <div
      className={cn(
        "border-2 border-line bg-panel p-5",
        raised && "border-line-strong",
        raised && !notched && (flare ? "shadow-slab-flare" : "shadow-slab"),
        notched && "notch-lg",
        className,
      )}
      {...props}
    />
  );
  // A clip-path would cut a box-shadow, so a notched panel casts its shadow from a wrapper.
  return raised && notched ? (
    <div
      className={
        flare
          ? "[filter:drop-shadow(6px_6px_0_var(--flare))]"
          : "[filter:drop-shadow(6px_6px_0_var(--seal))]"
      }
    >
      {panel}
    </div>
  ) : (
    panel
  );
}
