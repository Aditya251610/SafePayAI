import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

/**
 * /cases/[id] - case status tracker, offer card, human-review status, appeal
 * (REQ-WB-031/033/034, spec.md sec 2.10/2.12/2.13). Plain shadcn + light
 * Framer Motion only.
 *
 * Wave 4 renders ONE representative state (OFFERED, with the offer card) as
 * the skeleton proof - the full 12-state timeline mapping is copy-table
 * work (spec.md sec 2.13: "a copy-table entry, not invented per-screen")
 * that belongs in Wave 5, not invented here.
 *
 * TODO Wave 5:
 *   - Fetch GET /cases/{id}; map resolution's full state machine to
 *     buyer-friendly labels + timeline[] (REQ-WB-034).
 *   - Human-review state: neutral wording only ("A person is reviewing your
 *     case. Your coverage stays active.") - never risk reasoning,
 *     confidence, or words like flagged/suspicious/fraud/abuse
 *     (REQ-WB-033, banned list spec.md sec 5).
 *   - Offer card: exact refund amount, "why it applies" from
 *     decision.reasons[], who funds, expiry countdown, Approve/Decline as
 *     EQUAL-WEIGHT buttons (same size, no default focus bias), idempotent
 *     accept/decline (respondToOffer()).
 *   - Appeal: POST /cases/{id}/appeal.
 */
const MOCK_OFFER = {
  refundDisplay: "$24.00",
  why: "Your order was marked late under the terms you signed.",
  funder: "merchant, via PayPal refund",
  expiresIn: "24 hours (demo)",
};

export default async function CaseDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <div className="mx-auto max-w-xl px-4 py-12">
      <Card>
        <CardHeader>
          <CardTitle>Case {id}</CardTitle>
          <CardDescription>A refund offer is available for your review.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <p>
            <span className="font-medium">Refund amount:</span> {MOCK_OFFER.refundDisplay}
          </p>
          <p>
            <span className="font-medium">Why it applies:</span> {MOCK_OFFER.why}
          </p>
          <p>
            <span className="font-medium">Who funds it:</span> {MOCK_OFFER.funder}
          </p>
          <p>
            <span className="font-medium">Expires:</span> {MOCK_OFFER.expiresIn}
          </p>
          <p className="text-xs text-muted-foreground">
            Software rules decided this; AI did not. AI only read your message and summarized it.
          </p>

          <div className="grid grid-cols-2 gap-2">
            {/* TODO Wave 5: equal visual weight is required - do not let one
                button default-focus or visually dominate the other. */}
            <Button>Approve</Button>
            <Button variant="outline">Decline</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
