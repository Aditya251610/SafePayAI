"use client";

import { use } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

/**
 * /checkout/handoff/[id] - pre-redirect explainer before PayPal sandbox
 * approval (REQ-WB-027, spec.md sec 2.6). Plain shadcn + light Framer
 * Motion only - explicitly one of the WHERE-NOT-used screens
 * (tech-stack.md sec 3.2, spec.md sec 10).
 *
 * TODO Wave 5:
 *   - Fetch exact merchant/items/total from the real confirm response.
 *   - Open-redirect guard: validate approve_url's host against
 *     NEXT_PUBLIC_PS_WEB_PAYPAL_APPROVE_HOST_ALLOWLIST before navigating;
 *     mismatch -> error screen, no navigation, log it.
 *   - No PayPal logos/trademarks/SDK anywhere on this screen (prd.md sec 4).
 */
const MOCK_HANDOFF = {
  merchant: "Seeded Demo Store",
  items: ["Running socks x2"],
  totalDisplay: "$24.00",
};

export default function CheckoutHandoffPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  function handleApprove() {
    // TODO Wave 5: validate approve_url host allowlist, then
    // window.location.assign(approve_url).
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-12">
      <Card>
        <CardHeader>
          <CardTitle>Approve your purchase</CardTitle>
          <CardDescription>Cart {id}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm">
            You will approve this purchase on PayPal&apos;s sandbox site. No real money moves.
          </p>
          <dl className="space-y-1 text-sm">
            <div>
              <dt className="font-medium">Merchant</dt>
              <dd className="text-muted-foreground">{MOCK_HANDOFF.merchant}</dd>
            </div>
            <div>
              <dt className="font-medium">Items</dt>
              <dd className="text-muted-foreground">{MOCK_HANDOFF.items.join(", ")}</dd>
            </div>
            <div>
              <dt className="font-medium">Total</dt>
              <dd className="text-muted-foreground">{MOCK_HANDOFF.totalDisplay}</dd>
            </div>
          </dl>
          <Button onClick={handleApprove} className="w-full">
            Continue to PayPal sandbox
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
