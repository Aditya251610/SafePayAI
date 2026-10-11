import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * /policy (merchant) - read-only 3-rule policy view (REQ-WB-043,
 * spec.md sec 3.3). Plain shadcn + light Framer Motion only.
 *
 * Numbers below are placeholder/illustrative per prd.md non-goals ("no
 * authorization, price math, mandate evaluation, policy... logic in the
 * client" - these are display-only, sourced from the server in Wave 5).
 *
 * TODO Wave 5: per-case "which rules fired" breakdown sourced from
 * decision.reasons[].
 */
const RULES = [
  { name: "Refund cap", value: "~$50 cap" },
  { name: "Category exclusions", value: "Digital goods excluded" },
  { name: "Buyer velocity", value: ">2 refunds / 30 days -> human review" },
];

export default function MerchantPolicyPage() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Policy (read-only)</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {RULES.map((r) => (
          <p key={r.name}>
            <span className="font-medium">{r.name}:</span> {r.value}{" "}
            <span className="text-xs uppercase text-muted-foreground">illustrative</span>
          </p>
        ))}
      </CardContent>
    </Card>
  );
}
