"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";

/**
 * Global error boundary (spec.md sec 12): any unhandled client exception
 * shows this generic screen with a retry and a link to /about - never a
 * stack trace (fail-closed copy, REQ-WB-052 adjacent).
 */
export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="mx-auto flex min-h-[50vh] max-w-md flex-col items-center justify-center gap-4 px-4 text-center">
      <p className="text-sm text-muted-foreground">Something went wrong. Nothing was charged.</p>
      <div className="flex gap-2">
        <Button onClick={() => reset()}>Try again</Button>
        <Button asChild variant="outline">
          <Link href="/about">About this demo</Link>
        </Button>
      </div>
    </div>
  );
}
