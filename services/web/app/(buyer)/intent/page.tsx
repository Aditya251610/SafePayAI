"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

/**
 * /intent - intent textbox -> agent proposal (REQ-WB-023, spec.md sec 2.3).
 * Plain shadcn + light Framer Motion only.
 *
 * TODO Wave 5:
 *   - Enforce PS_SHOPPINGAGENT_INTENT_MAX_CHARS (<=500 per spec.md) - not
 *     hardcoded here since that's a server-config-driven value.
 *   - Call proposeCart() via lib/api-client.ts; on source:"cached" render
 *     the CACHED badge text verbatim from the response, never invented.
 *   - On status NO_MATCH | NO_PROPOSAL | AI_PAUSED, fall back to the manual
 *     catalog cart builder (not yet a separate route in this skeleton -
 *     TODO: decide whether that's a mode of /cart/[id] or its own route).
 */
export default function IntentPage() {
  const [intent, setIntent] = useState("");

  return (
    <div className="mx-auto max-w-xl px-4 py-12">
      <Card>
        <CardHeader>
          <CardTitle>What are you shopping for?</CardTitle>
          <CardDescription>
            The assistant proposes a cart from a small seeded catalog. You can always build one
            yourself.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <textarea
            value={intent}
            onChange={(e) => setIntent(e.target.value)}
            maxLength={500}
            aria-label="Shopping intent"
            placeholder="e.g. birthday gift for a runner under $60"
            className="min-h-24 w-full rounded-md border bg-background p-3 text-sm"
          />
          <p className="text-xs text-muted-foreground">{intent.length}/500</p>
          {/* TODO Wave 5: call proposeCart(), route to /cart/[id] on success. */}
          <Button disabled={intent.length === 0} className="w-full">
            Propose a cart
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
