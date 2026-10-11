import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

/**
 * /cart/[id] - cart proposal / BLOCKED / NEEDS_BUYER_CONFIRMATION screen
 * (REQ-WB-024/025/026, spec.md sec 2.3-2.5). Plain shadcn + light Framer
 * Motion only (money-path - no WebGL/Aceternity).
 *
 * MOCK DATA below is illustrative, clearly not server data. Shown here with
 * a BLOCK check so the no-Confirm-button-when-blocked rule (REQ-WB-025) is
 * visible in the skeleton - this is the exact scenario the "Over-cap block"
 * guardrail demo scene exercises (spec.md sec 4).
 *
 * TODO Wave 5:
 *   - Fetch the real cart by [id]; render checks[] rows: PASS (grey),
 *     BLOCK (red, reason_code -> copy table sec 10), TIGHTEN/advisory
 *     (blue, "advisory, can only tighten, cannot clear a block").
 *   - If status === "BLOCKED": render ZERO Confirm control (not just
 *     disabled - absent), only "Edit cart" / "Change mandate" links.
 *   - If status === "NEEDS_BUYER_CONFIRMATION": require an explicit
 *     checkbox before Confirm enables, mapped to confirm_intent_fit: true.
 *   - On confirm: POST /carts/{id}/confirm, then route to
 *     /checkout/handoff/[id].
 */
const MOCK_CART = {
  id: "cart_mock_001",
  status: "BLOCKED" as const,
  totalDisplay: "$84.00",
  remainingCapDisplay: "$60.00",
  checks: [
    { sku: "SKU-1", status: "BLOCK" as const, reasonText: "This cart is over your mandate's maximum total." },
    { sku: "SKU-2", status: "PASS" as const, reasonText: "Within mandate terms." },
  ],
};

export default async function CartPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const isBlocked = MOCK_CART.status === "BLOCKED";

  return (
    <div className="mx-auto max-w-xl px-4 py-12">
      <Card>
        <CardHeader>
          <CardTitle>Cart {id}</CardTitle>
          <CardDescription>
            Total {MOCK_CART.totalDisplay} - remaining cap {MOCK_CART.remainingCapDisplay}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {isBlocked && (
            <div role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
              This cart is blocked and cannot be confirmed.
            </div>
          )}

          <ul className="space-y-2 text-sm">
            {MOCK_CART.checks.map((c) => (
              <li
                key={c.sku}
                className={
                  c.status === "BLOCK"
                    ? "text-destructive"
                    : c.status === "PASS"
                      ? "text-muted-foreground"
                      : "text-blue-600"
                }
              >
                {c.status === "BLOCK" ? "Blocked: " : c.status === "PASS" ? "OK: " : "Advisory: "}
                {c.reasonText}
              </li>
            ))}
          </ul>

          {isBlocked ? (
            <div className="flex gap-2">
              <Button asChild variant="outline">
                <Link href="/intent">Edit cart</Link>
              </Button>
              <Button asChild variant="outline">
                <Link href="/mandate/new">Change mandate</Link>
              </Button>
            </div>
          ) : (
            // TODO Wave 5: only rendered when not blocked; confirm -> handoff.
            <Button className="w-full">Confirm and continue</Button>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
