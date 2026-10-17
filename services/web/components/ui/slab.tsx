import * as React from "react";

import { cn } from "@/lib/utils";

interface SlabProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Hard offset shadow for the one panel that needs the eye. */
  raised?: boolean;
  /** Angled top-right corner. */
  notched?: boolean;
}

/** The panel surface: a 2 px line border on the panel colour. */
export function Slab({ className, raised, notched, ...props }: SlabProps) {
  return (
    <div
      className={cn(
        "border-2 border-line bg-panel p-5",
        raised && "border-fg shadow-slab",
        notched && "notch-lg",
        className,
      )}
      {...props}
    />
  );
}
