import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

/**
 * /approve/[token] - out-of-terms approval link (REQ-WB-032,
 * spec.md sec 2.11). Plain shadcn + light Framer Motion only.
 *
 * TODO Wave 5:
 *   - GET /approvals/{token} server-side before any state change; requires
 *     the same buyer session (mismatch -> generic "This link isn't for your
 *     session" message, no existence oracle).
 *   - Fresh CSRF nonce required on confirm.
 *   - Handle APPROVAL_REPLAY (409 -> "Already used"), APPROVAL_EXPIRED
 *     (-> "Expired, your case moved to human review"), APPROVAL_REVOKED,
 *     wrong-session (generic 404-style message).
 */
const MOCK_TERMS = {
  summary: "Approve an additional $10.00 refund outside your original mandate terms.",
};

export default async function OutOfTermsApprovalPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return (
    <div className="mx-auto max-w-xl px-4 py-12">
      <Card>
        <CardHeader>
          <CardTitle>Review this request</CardTitle>
          <CardDescription>Token: {token}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <p>{MOCK_TERMS.summary}</p>
          {/* TODO Wave 5: wire confirm to the real approval endpoint with a fresh CSRF nonce. */}
          <Button className="w-full">Approve</Button>
        </CardContent>
      </Card>
    </div>
  );
}
