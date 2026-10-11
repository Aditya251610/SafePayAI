import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

// shadcn/ui's standard class-merging helper. Used by every ui/* component.
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
