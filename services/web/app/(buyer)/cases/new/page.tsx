"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

/**
 * /cases/new - report a problem (REQ-WB-030, spec.md sec 2.9). Plain
 * shadcn + light Framer Motion only.
 *
 * TODO Wave 5:
 *   - Character cap from server config (PS_RESOLUTION_CASE_REPORT_MAX_CHARS)
 *     - not hardcoded here, placeholder 1000 below.
 *   - Order picker scoped to the buyer's own orders only.
 *   - On submit: ALWAYS show the neutral confirmation copy below,
 *     regardless of the triage outcome - never surface category/confidence
 *     to the buyer.
 *   - Rendered-back text uses React's default escaping only -
 *     dangerouslySetInnerHTML is banned (REQ-WB-006, enforced by eslint
 *     react/no-danger).
 */
export default function ReportProblemPage() {
  const [text, setText] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const maxChars = 1000; // TODO Wave 5: replace with server-config value.

  if (submitted) {
    return (
      <div className="mx-auto max-w-md px-4 py-12 text-center text-sm text-muted-foreground">
        We&apos;ve logged this and are looking into it.
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-12">
      <Card>
        <CardHeader>
          <CardTitle>Report a problem</CardTitle>
          <CardDescription>Tell us what happened with your order.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={maxChars}
            aria-label="Describe the problem"
            className="min-h-32 w-full rounded-md border bg-background p-3 text-sm"
          />
          <p className="text-xs text-muted-foreground">
            {text.length}/{maxChars}
          </p>
          {/* TODO Wave 5: call reportProblem({orderId, text}) via lib/api-client.ts. */}
          <Button onClick={() => setSubmitted(true)} disabled={text.length === 0} className="w-full">
            Submit
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
