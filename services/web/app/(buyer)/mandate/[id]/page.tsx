"use client";

import { use, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogTrigger,
} from "@/components/ui/dialog";

/**
 * /mandate/[id] - mandate summary + Revoke action (REQ-WB-022,
 * spec.md sec 2.2). Plain shadcn + light Framer Motion only (money-path).
 *
 * MOCK DATA is illustrative placeholder, not a real mandate record.
 *
 * TODO Wave 5:
 *   - Fetch the real mandate by [id] via lib/api-client.ts.
 *   - Wire the Revoke confirmation modal to revokeMandate(); show both
 *     effects (stops future purchases; already-captured protection stands)
 *     and map `message_code` (e.g. FUTURE_PURCHASES_STOPPED) to buyer copy.
 */
const MOCK_MANDATE = {
  id: "mandate_mock_001",
  remainingCapDisplay: "$60.00",
  status: "ACTIVE",
};

export default function MandateSummaryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [revoked, setRevoked] = useState(false);

  return (
    <div className="mx-auto max-w-xl px-4 py-12">
      <Card>
        <CardHeader>
          <CardTitle>Mandate {id}</CardTitle>
          <CardDescription>Status: {revoked ? "REVOKED" : MOCK_MANDATE.status}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Remaining cap: {MOCK_MANDATE.remainingCapDisplay}
          </p>

          <Dialog>
            <DialogTrigger asChild>
              <Button variant="destructive" disabled={revoked}>
                Revoke mandate
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Revoke this mandate?</DialogTitle>
                <DialogDescription>
                  You won&apos;t be able to start new purchases with this mandate. Protection for
                  purchases you already completed is not reversed.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                {/* TODO Wave 5: call revokeMandate(id), show released_reservations. */}
                <Button variant="destructive" onClick={() => setRevoked(true)}>
                  Confirm revoke
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardContent>
      </Card>
    </div>
  );
}
