import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const tagVariants = cva(
  "inline-flex h-7 items-center gap-2 whitespace-nowrap border-2 px-2.5 text-[11px] font-bold uppercase tracking-[0.1em]",
  {
    variants: {
      tone: {
        neutral: "border-line-strong text-mute",
        seal: "border-seal text-seal",
        flare: "border-flare text-flare",
        ret: "border-ret text-ret",
        solid: "border-fg bg-fg text-bg",
        "solid-seal": "border-seal bg-seal text-on-seal",
        "solid-ret": "border-ret bg-ret text-on-ret",
        "solid-flare": "border-flare bg-flare text-bg",
        dashed: "border-dashed border-line-strong text-dim",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export interface TagProps
  extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof tagVariants> {}

export function Tag({ className, tone, ...props }: TagProps) {
  return <span className={cn(tagVariants({ tone }), className)} {...props} />;
}
