import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

/**
 * /review (merchant) - human-review queue + override (REQ-WB-044,
 * spec.md sec 3.4). Plain shadcn + light Framer Motion only.
 *
 * Wave 4: plain table placeholder. AG Grid Community (WEB-S4-01) lands
 * later, and per R10 the detail pane lives OUTSIDE the grid, never a
 * grid master/detail Enterprise feature.
 *
 * TODO Wave 5:
 *   - Fetch GET /review/queue via getReviewQueue(); columns case id, kind,
 *     reason codes, age, SLA state (WITHIN/OVER/NO_TARGET, labelled
 *     illustrative/demo when present).
 *   - Detail pane with Override -> POST /cases/{id}/merchant-action
 *     {"type":"OVERRIDE_OFFER"}; state plainly: "This creates a new offer.
 *     The buyer must still approve it. No money moves yet."
 */
export default function MerchantReviewQueuePage() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Human-review queue</CardTitle>
        <CardDescription>Not yet wired (Wave 5).</CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">No cases to show in this skeleton.</p>
      </CardContent>
    </Card>
  );
}
