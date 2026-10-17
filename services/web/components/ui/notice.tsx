import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const noticeVariants = cva("border-2 border-l-8 bg-panel px-4 py-3 text-sm", {
  variants: {
    tone: {
      info: "border-seal",
      warn: "border-flare",
      ok: "border-ret",
    },
  },
  defaultVariants: { tone: "info" },
});

interface NoticeProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title">, VariantProps<typeof noticeVariants> {
  title?: string;
}

/** Inline message. Warnings and errors use role=alert so they are announced. */
export function Notice({ className, tone, title, children, ...props }: NoticeProps) {
  return (
    <div
      role={tone === "warn" ? "alert" : "status"}
      className={cn(noticeVariants({ tone }), className)}
      {...props}
    >
      {title && <p className="mb-1 text-[11px] font-bold uppercase tracking-[0.12em]">{title}</p>}
      <div className="text-mute">{children}</div>
    </div>
  );
}
