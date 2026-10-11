import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

/**
 * /orders (merchant) - orders table + SIMULATED CARRIER controls + demo
 * clock panel (REQ-WB-040/041, spec.md sec 3.1). Plain shadcn + light
 * Framer Motion only (merchant trust screen).
 *
 * Wave 4 renders a plain HTML table (sprint-tasks.md WEB-S3-01: "plain
 * table first, AG Grid deferred to S4 per cut-order"; AG Grid itself is
 * WEB-S4-01, not yet built in this skeleton). Community-edition-only AG
 * Grid lands later per spec.md sec 9/R8.
 *
 * MOCK DATA is illustrative only.
 *
 * TODO Wave 5:
 *   - Fetch via listMerchantOrders() (lib/api-client.ts).
 *   - Columns: order id, buyer id (ephemeral, opaque), items, total, state,
 *     tracking status, SIMULATED CARRIER badge cell, promise date.
 *   - Per-row add-tracking, force-carrier-status (explicit confirm dialog
 *     restating "this does not reflect a real carrier").
 *   - Shared demo clock panel, visible only when
 *     NEXT_PUBLIC_PS_WEB_DEMO_MODE=true.
 */
const MOCK_ORDERS = [
  { id: "order_mock_001", buyerId: "buyer_ephemeral_abc", total: "$24.00", state: "RESOLVED_REFUNDED" },
];

export default function MerchantOrdersPage() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Orders</CardTitle>
        <CardDescription>SIMULATED CARRIER - demo clock panel not yet wired (Wave 5)</CardDescription>
      </CardHeader>
      <CardContent>
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b">
              <th className="py-2">Order</th>
              <th className="py-2">Buyer</th>
              <th className="py-2">Total</th>
              <th className="py-2">State</th>
            </tr>
          </thead>
          <tbody>
            {MOCK_ORDERS.map((o) => (
              <tr key={o.id} className="border-b last:border-0">
                <td className="py-2">{o.id}</td>
                <td className="py-2 text-muted-foreground">{o.buyerId}</td>
                <td className="py-2">{o.total}</td>
                <td className="py-2">{o.state}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
