"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

/**
 * /controls (merchant) - REFUNDS_FROZEN switch + demo reset
 * (REQ-WB-046/047, spec.md sec 3.6/3.7/sec 8). Plain shadcn + light Framer
 * Motion only.
 *
 * TODO Wave 5:
 *   - GET /controls/refunds-frozen; toggle requires a non-empty reason
 *     (matches REASON_REQUIRED 422) + confirm step.
 *   - Frozen state shown here; on the buyer side it must render as the
 *     neutral "Refunds are paused for review" note (never "frozen" or any
 *     alarming word to the buyer, per spec.md sec 3.6).
 *   - Demo reset: visible only when NEXT_PUBLIC_PS_WEB_DEMO_MODE=true,
 *     typed confirmation (e.g. type "RESET"), disabled while in flight,
 *     success toast states the new chain epoch.
 */
export default function MerchantControlsPage() {
  const [frozen, setFrozen] = useState(false);
  const [resetConfirmText, setResetConfirmText] = useState("");
  const demoMode = process.env.NEXT_PUBLIC_PS_WEB_DEMO_MODE === "true";

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Refunds frozen</CardTitle>
          <CardDescription>
            Current: {frozen ? "FROZEN" : "ACTIVE"} (not wired to the gateway yet)
          </CardDescription>
        </CardHeader>
        <CardContent>
          {/* TODO Wave 5: require a non-empty reason before toggling. */}
          <Button variant={frozen ? "secondary" : "destructive"} onClick={() => setFrozen((f) => !f)}>
            {frozen ? "Unfreeze refunds" : "Freeze refunds"}
          </Button>
        </CardContent>
      </Card>

      {demoMode && (
        <Card>
          <CardHeader>
            <CardTitle>Demo reset</CardTitle>
            <CardDescription>Type RESET to confirm. Starts a new chain epoch.</CardDescription>
          </CardHeader>
          <CardContent className="flex gap-2">
            <input
              value={resetConfirmText}
              onChange={(e) => setResetConfirmText(e.target.value)}
              aria-label="Type RESET to confirm"
              className="rounded-md border bg-background px-3 py-2 text-sm"
            />
            {/* TODO Wave 5: call the admin-token-protected reset endpoint. */}
            <Button variant="destructive" disabled={resetConfirmText !== "RESET"}>
              Reset demo data
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
