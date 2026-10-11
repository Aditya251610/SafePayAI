"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

/**
 * /start - ephemeral buyer session creation (REQ-WB-010, spec.md IA).
 *
 * TODO Wave 5: call the real session-creation BFF endpoint via
 * lib/api-client.ts, store nothing in localStorage/sessionStorage
 * (REQ-WB-011 - gateway cookie + in-memory CSRF only), then route to
 * /mandate/new.
 */
export default function StartSessionPage() {
  const router = useRouter();
  const [creating, setCreating] = useState(false);

  async function handleStart() {
    setCreating(true);
    // TODO Wave 5: await createBuyerSession() from lib/api-client.ts.
    // Mock delay stands in for the real network round trip in this skeleton.
    await new Promise((r) => setTimeout(r, 300));
    setCreating(false);
    router.push("/mandate/new");
  }

  return (
    <div className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center px-4">
      <Card className="w-full">
        <CardHeader>
          <CardTitle>Start your demo session</CardTitle>
          <CardDescription>
            Creates an ephemeral buyer session. No account, no real payment info.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button onClick={handleStart} disabled={creating} className="w-full">
            {creating ? "Starting..." : "Start as buyer"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
