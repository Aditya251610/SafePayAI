import { METER_CELLS, meterCells } from "@/lib/format/meter";
import { cn } from "@/lib/utils";

interface MeterProps {
  /** Spent portion and the whole cap, in the same unit. Only the ratio is drawn. */
  part: number;
  whole: number;
  /** Optional second segment, such as the cart being reviewed. */
  extra?: number;
  label: string;
  className?: string;
}

/** The 20-cell cap meter. The text next to it carries the real figures. */
export function Meter({ part, whole, extra = 0, label, className }: MeterProps) {
  const spent = meterCells(part, whole);
  const withExtra = meterCells(part + extra, whole);
  return (
    <div
      role="img"
      aria-label={label}
      className={cn("grid gap-[3px]", className)}
      style={{ gridTemplateColumns: `repeat(${METER_CELLS}, minmax(0, 1fr))` }}
    >
      {Array.from({ length: METER_CELLS }, (_, i) => (
        <div
          key={i}
          data-cell={i < spent ? "spent" : i < withExtra ? "extra" : "free"}
          className={cn(
            "box-border h-5",
            i < spent && "bg-fg",
            i >= spent && i < withExtra && "bg-flare",
            i >= withExtra && "border border-line-strong",
          )}
        />
      ))}
    </div>
  );
}
