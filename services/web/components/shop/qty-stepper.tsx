"use client";

import { Button } from "@/components/ui/button";
import { MAX_QTY } from "@/lib/shop/catalog";

/** Quantity 1..5 with 48 px targets. */
export function QtyStepper({
  value,
  onChange,
  label,
}: {
  value: number;
  onChange: (n: number) => void;
  label: string;
}) {
  return (
    <div role="group" aria-label={`Quantity for ${label}`} className="flex items-center">
      <Button
        variant="secondary"
        size="icon"
        aria-label={`Decrease quantity of ${label}`}
        disabled={value <= 1}
        onClick={() => onChange(value - 1)}
      >
        −
      </Button>
      <span className="tabular w-10 text-center font-semibold" aria-live="polite">
        {value}
      </span>
      <Button
        variant="secondary"
        size="icon"
        aria-label={`Increase quantity of ${label}`}
        disabled={value >= MAX_QTY}
        onClick={() => onChange(value + 1)}
      >
        +
      </Button>
    </div>
  );
}
