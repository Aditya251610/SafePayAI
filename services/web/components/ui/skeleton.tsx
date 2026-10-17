import { cn } from "@/lib/utils";

/** Placeholder block while data loads. Pulse stops under reduced motion. */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn("animate-pulse bg-panel-2 motion-reduce:animate-none", className)}
    />
  );
}
