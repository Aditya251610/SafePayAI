import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

/**
 * /orders/[id] (merchant) - AI brief panel + tracking form
 * (REQ-WB-042, spec.md sec 3.2). Plain shadcn + light Framer Motion only.
 *
 * TODO Wave 5:
 *   - Raw buyer text (verbatim, escaped) beside AI summary/category/
 *     confidence; "advisory; AI does not decide refunds" banner ALWAYS
 *     visible above the panel, not just on hover.
 *   - Policy decision (from resolution, not triage) in a visually separate
 *     card with its own heading - a merchant must not mistake the AI
 *     output for the decision.
 *   - Draft messages, if built, marked "draft, not sent", no send button
 *     wired to anything real.
 *   - addTracking() call via lib/api-client.ts.
 */
const MOCK_BRIEF = {
  rawText: "it never showed up, its been like 2 weeks",
  aiSummary: "Buyer reports non-delivery after an extended period.",
  aiCategory: "LATE",
  aiConfidence: 0.82,
};

export default async function MerchantOrderDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <div className="space-y-4">
      <div className="rounded-md border border-amber-500/50 bg-amber-500/10 p-3 text-sm">
        Advisory; AI does not decide refunds.
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Raw buyer text</CardTitle>
            <CardDescription>Order {id}</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm">{MOCK_BRIEF.rawText}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>AI summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <p>{MOCK_BRIEF.aiSummary}</p>
            <p className="text-muted-foreground">
              Category: {MOCK_BRIEF.aiCategory} - confidence {MOCK_BRIEF.aiConfidence}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Policy decision</CardTitle>
          <CardDescription>Separate from the AI output above.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Not yet wired (Wave 5) - will render decision.reasons[] from resolution.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
