import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

/**
 * "Your demo session ended" screen (REQ-WB-012). Shown whenever the gateway
 * returns 401. Plain shadcn only - no motion needed beyond the global
 * route-transition fade (money/trust-adjacent, keep it legible).
 *
 * TODO Wave 5: wire this as the global 401 handler in lib/api-client.ts
 * (redirect here, or render this in place, on any 401 response) and the
 * one-click "start a new session" button to the real session-creation call.
 * In-progress non-money-sensitive form text should be preserved via local
 * component state only (never persisted to storage) - not implemented yet.
 */
export default function SessionEndedPage() {
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center px-4">
      <Card className="w-full">
        <CardHeader>
          <CardTitle>Your demo session ended</CardTitle>
          <CardDescription>Nothing was charged. Start a new session to continue.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild className="w-full">
            <Link href="/start">Start a new session</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
