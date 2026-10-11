"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

/**
 * /audit (merchant) - audit log + Verify-chain button + head hash
 * (REQ-WB-045, spec.md sec 3.5). Plain shadcn + light Framer Motion only -
 * explicitly a WHERE-NOT screen for WebGL/Aceternity (spec.md sec 10).
 *
 * TODO Wave 5:
 *   - Fetch GET /audit/entries via getAuditEntries(); columns seq, type,
 *     actor_type/actor_id, ts, record_hash (truncated, full on row
 *     expand).
 *   - Verify chain button calls verifyAuditChain(); show OK/FAILED banner
 *     prominently, head hash with copy-to-clipboard, chain epoch (so a
 *     demo reset reads as a new epoch, never "history was deleted").
 */
export default function MerchantAuditPage() {
  const [result, setResult] = useState<"idle" | "ok" | "failed">("idle");

  function handleVerify() {
    // TODO Wave 5: await verifyAuditChain() from lib/api-client.ts.
    setResult("ok");
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Audit log</CardTitle>
          <CardDescription>Tamper-evident, hash-chained. Not yet wired (Wave 5).</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button onClick={handleVerify}>Verify chain</Button>
          {result !== "idle" && (
            <div
              role="status"
              className={
                result === "ok"
                  ? "rounded-md border border-green-500/50 bg-green-500/10 p-3 text-sm"
                  : "rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm"
              }
            >
              {result === "ok" ? "OK (mock result - not wired yet)" : "FAILED"}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
