import * as React from "react";

import { cn } from "@/lib/utils";

interface FieldProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
  error?: string;
}

/** Labelled text input. The id is required so the label is always connected. */
export const Field = React.forwardRef<HTMLInputElement, FieldProps & { id: string }>(
  ({ label, hint, error, className, id, ...props }, ref) => {
    const describedBy = [hint ? `${id}-hint` : null, error ? `${id}-error` : null]
      .filter(Boolean)
      .join(" ");
    return (
      <div className="flex flex-col gap-1.5">
        <label htmlFor={id} className="text-[11px] font-bold uppercase tracking-[0.14em] text-dim">
          {label}
        </label>
        <input
          ref={ref}
          id={id}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy || undefined}
          className={cn(
            "h-12 border-2 bg-panel px-3 text-base text-fg placeholder:text-dim",
            error ? "border-flare" : "border-line-strong focus:border-fg",
            className,
          )}
          {...props}
        />
        {hint && (
          <p id={`${id}-hint`} className="text-xs text-dim">
            {hint}
          </p>
        )}
        {error && (
          <p id={`${id}-error`} role="alert" className="text-xs font-semibold text-flare">
            {error}
          </p>
        )}
      </div>
    );
  },
);
Field.displayName = "Field";
