"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { ApiError } from "@/lib/api/errors";
import { errorCopy } from "@/lib/api/messages";

/** Counts down a Retry-After value in whole seconds. */
export function useCountdown(seconds: number | null): number {
  const [left, setLeft] = React.useState(seconds ?? 0);
  React.useEffect(() => {
    setLeft(seconds ?? 0);
    if (!seconds) return;
    const id = setInterval(() => setLeft((n) => (n > 0 ? n - 1 : 0)), 1000);
    return () => clearInterval(id);
  }, [seconds]);
  return left;
}

/** The one place API failures are shown to people. */
export function ApiErrorNotice({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const err = error instanceof ApiError ? error : null;
  const copy = errorCopy(err?.code ?? "NETWORK_ERROR");
  const wait = useCountdown(err?.retryAfterS ?? null);

  return (
    <Notice tone="warn" title={copy.title} className={className}>
      <p>{copy.text}</p>
      {err?.fields.length ? (
        <ul className="mt-2 list-disc pl-5">
          {err.fields.map((f) => (
            <li key={`${f.field}:${f.message}`}>
              {f.field ? `${f.field}: ` : ""}
              {f.message}
            </li>
          ))}
        </ul>
      ) : null}
      {wait > 0 && <p className="mt-2 font-semibold">Try again in {wait}s.</p>}
      {copy.retryable && onRetry && (
        <Button
          className="mt-3"
          size="sm"
          variant="secondary"
          disabled={wait > 0}
          onClick={onRetry}
        >
          Try again
        </Button>
      )}
      {err?.requestId && (
        <p className="mt-3 font-mono text-[11px] text-dim">Reference {err.requestId}</p>
      )}
    </Notice>
  );
}
