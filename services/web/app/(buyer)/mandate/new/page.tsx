"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

/**
 * /mandate/new - mandate preview + sign screen (REQ-WB-020/021,
 * spec.md sec 2.1). Plain shadcn + light Framer Motion only - this is a
 * money-path/trust screen, no WebGL/Aceternity (spec.md sec 10 WHERE-NOT
 * list).
 *
 * MOCK DATA below is illustrative only, clearly not from the server -
 * replace with the real `preview` response (merchants, max_total major
 * units + currency, intent, expiry, protection promise) in Wave 5.
 *
 * TODO Wave 5:
 *   - GET/POST preview via lib/api-client.ts previewMandate(); render the
 *     real nonce (shown once) in the collapsed Details section.
 *   - Sign button: require fresh CSRF + the preview nonce, call
 *     signMandate(), handle NONCE_INVALID / SCREEN_TEXT_MISMATCH (re-preview
 *     with "terms refreshed" note) and TERMS_OUT_OF_BOUNDS /
 *     UNSUPPORTED_CURRENCY (inline field errors).
 *   - States: draft -> previewing -> signing (disabled button + spinner) ->
 *     signed (redirect to /mandate/[id]).
 *   - Integers must never be shown - all amounts are formatted from
 *     *_minor to major units for display only, no client math.
 */
const MOCK_PREVIEW = {
  merchants: ["Seeded Demo Store"],
  maxTotalDisplay: "$60.00",
  intent: "birthday gift for a runner under $60",
  expiry: "in 24 hours (demo)",
  revokeNote: "Stops future spending. A purchase you already completed keeps its protection.",
};

export default function MandateNewPage() {
  return (
    <div className="mx-auto max-w-xl px-4 py-12">
      <Card>
        <CardHeader>
          <CardTitle>Sign your mandate</CardTitle>
          <CardDescription>Plain-language terms - read before signing.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <dl className="space-y-2 text-sm">
            <div>
              <dt className="font-medium">Merchants</dt>
              <dd className="text-muted-foreground">{MOCK_PREVIEW.merchants.join(", ")}</dd>
            </div>
            <div>
              <dt className="font-medium">Maximum total</dt>
              <dd className="text-muted-foreground">{MOCK_PREVIEW.maxTotalDisplay}</dd>
            </div>
            <div>
              <dt className="font-medium">Intent</dt>
              <dd className="text-muted-foreground">{MOCK_PREVIEW.intent}</dd>
            </div>
            <div>
              <dt className="font-medium">Expiry</dt>
              <dd className="text-muted-foreground">{MOCK_PREVIEW.expiry}</dd>
            </div>
            <div>
              <dt className="font-medium">Revoke</dt>
              <dd className="text-muted-foreground">{MOCK_PREVIEW.revokeNote}</dd>
            </div>
          </dl>

          <details className="rounded-md border p-3 text-xs text-muted-foreground">
            <summary className="cursor-pointer font-medium text-foreground">Details</summary>
            {/* TODO Wave 5: policy_version, nonce, screen_text_hash, server attestation note. */}
            <p className="mt-2">
              policy_version, nonce, and screen_text_hash will render here once wired to the real
              preview response (Wave 5).
            </p>
          </details>

          {/* TODO Wave 5: disable while signing; show spinner; call signMandate(). */}
          <Button className="w-full">Sign mandate</Button>
        </CardContent>
      </Card>
    </div>
  );
}
