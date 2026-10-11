import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * /orders/[id]/receipt - receipt (REQ-WB-029, spec.md sec 2.8). Plain
 * shadcn + light Framer Motion only - explicitly WHERE-NOT for
 * WebGL/Aceternity (spec.md sec 10); also has @media print rules in
 * app/globals.css.
 *
 * MOCK DATA is illustrative placeholder only. `disclosures` here mirrors
 * the exact server-owned wording pattern (rendered verbatim, never
 * paraphrased, per spec.md sec 2.8/5) - replace with the real
 * receipt.disclosures[] array in Wave 5, do not invent new wording.
 *
 * TODO Wave 5:
 *   - Fetch GET /orders/{id}/receipt via lib/api-client.ts getReceipt().
 *   - Render checks[] reasons, PayPal order_id/capture_id, mandate
 *     reference.
 *   - "Protected until day X (demo)" with an ILLUSTRATIVE tooltip exactly
 *     as specified (demo clock day, not a calendar date, not PayPal's own
 *     window).
 */
const MOCK_RECEIPT = {
  items: ["Running socks x2"],
  merchant: "Seeded Demo Store",
  totalDisplay: "$24.00",
  mandateRef: "mandate_mock_001",
  orderId: "order_mock_001",
  captureId: "capture_mock_001",
  protectedUntilDay: 7,
  disclosures: [
    "Refund, if any, is merchant-funded via PayPal refund.",
    "Carrier status shown on this order is simulated.",
  ],
};

export default async function ReceiptPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <div className="mx-auto max-w-xl px-4 py-12 print:py-0">
      <Card>
        <CardHeader>
          <CardTitle>Receipt - order {id}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p>
            <span className="font-medium">Merchant:</span> {MOCK_RECEIPT.merchant}
          </p>
          <p>
            <span className="font-medium">Items:</span> {MOCK_RECEIPT.items.join(", ")}
          </p>
          <p>
            <span className="font-medium">Total:</span> {MOCK_RECEIPT.totalDisplay}
          </p>
          <p>
            <span className="font-medium">Mandate reference:</span> {MOCK_RECEIPT.mandateRef}
          </p>
          <p>
            <span className="font-medium">PayPal order / capture:</span> {MOCK_RECEIPT.orderId} /{" "}
            {MOCK_RECEIPT.captureId}
          </p>
          <p title="Demo clock day, not a calendar date, not PayPal's own window. ILLUSTRATIVE.">
            <span className="font-medium">Protected until day {MOCK_RECEIPT.protectedUntilDay}</span>{" "}
            <span className="text-xs uppercase text-muted-foreground">(demo, illustrative)</span>
          </p>
          <p className="text-xs uppercase text-muted-foreground">Simulated carrier</p>
          <ul className="list-disc pl-5 text-muted-foreground">
            {MOCK_RECEIPT.disclosures.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
