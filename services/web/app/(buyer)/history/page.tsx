import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * /history - mandates, orders, cases for this buyer (REQ-WB-035,
 * spec.md sec 2.14). Plain shadcn + light Framer Motion only.
 *
 * TODO Wave 5: fetch each list via its own cursor/limit pagination; deep
 * link each row to /mandate/[id], /orders/[id]/receipt, /cases/[id].
 */
export default function HistoryPage() {
  return (
    <div className="mx-auto max-w-xl space-y-6 px-4 py-12">
      <Card>
        <CardHeader>
          <CardTitle>Your history</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Mandates, orders, and cases will list here once wired to the gateway (Wave 5).
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
