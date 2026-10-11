"use client";

import { motion } from "framer-motion";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * /about - honesty page (REQ-WB-005). Mirrors README limitations. This is
 * NOT a money-path screen but spec.md sec 10 lists it as a "transitions
 * between major sections" example where light Framer Motion (simple
 * opacity/fade) is fine - no WebGL/Aceternity here either way, since this
 * page's whole job is making disclosures legible, not visual impact.
 *
 * Content below is the real disclosure list from prd.md REQ-WB-005 - this
 * is copy, not business logic, so it is written out in full rather than
 * left as a comment placeholder.
 */
const DISCLOSURES = [
  "This is a sandbox demo. No real money moves.",
  "Carrier tracking status is simulated and stored in our own database, not a real carrier.",
  "The product catalog is a small seeded set (about a dozen items, three virtual merchants settling to one sandbox merchant).",
  "Mandate signing uses server-side attestation (HMAC, demo-grade) - it is not a buyer-held cryptographic signature.",
  "The \"protected until day X\" window is a demo clock, not a calendar date and not PayPal's own protection window.",
  "A refund, when issued, is merchant-funded via a real PayPal sandbox refund call.",
  "There is one shared merchant demo login, disclosed here and on the merchant screens.",
  "Untested in this build: webhooks (we poll instead), the Disputes API, and refunds that return a PENDING status.",
];

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-12">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
        <Card>
          <CardHeader>
            <CardTitle>About this demo</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc space-y-2 pl-5 text-sm text-muted-foreground">
              {DISCLOSURES.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}
