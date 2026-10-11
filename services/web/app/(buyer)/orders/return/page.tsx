"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { WakingUp } from "@/components/shared/waking-up";

/**
 * /orders/return - PayPal return handler (REQ-WB-028, spec.md sec 2.7).
 * Plain shadcn + light Framer Motion only.
 *
 * TODO Wave 5:
 *   - On mount: history.replaceState to strip state/token/PayerID from the
 *     address bar immediately (never let them linger, Referrer-Policy
 *     no-referrer is set server-side but this is belt-and-suspenders).
 *   - Call completeReturn({state, token, payerId}) via lib/api-client.ts.
 *     NEVER capture client-side - this call only forwards the three values;
 *     the server does the real capture.
 *   - Map response codes to copy exactly (fail-closed, REQ-WB-052):
 *     NOT_APPROVED, STATE_INVALID/TOKEN_MISMATCH, SIGN_IN_REQUIRED,
 *     MANDATE_REVOKED/CANCELLED_REVOKED, CAPTURE_UNKNOWN/PAYPAL_UNAVAILABLE
 *     (poll/retry GET /orders/{id}, never say "payment failed" when the
 *     true state is unknown).
 *   - Success -> redirect to /orders/[id]/receipt.
 *
 * `useSearchParams()` requires a Suspense boundary during static export
 * (Next.js CSR bailout rule) - split into an inner component for that.
 */
function ReturnHandler() {
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<"confirming" | "waking" | "error">("confirming");

  useEffect(() => {
    // Capture the PayPal params BEFORE stripping them from the address bar.
    const state = searchParams.get("state");
    const token = searchParams.get("token");
    const payerId = searchParams.get("PayerID");

    if (typeof window !== "undefined") {
      window.history.replaceState({}, "", window.location.pathname);
    }

    // TODO Wave 5: await completeReturn({ state, token, payerId }) from
    // lib/api-client.ts and route to the receipt on success. Mock: this
    // skeleton never leaves "confirming" because nothing is wired yet.
    void state;
    void token;
    void payerId;
    setStatus("confirming");
  }, [searchParams]);

  if (status === "waking") return <WakingUp />;

  return (
    <div className="mx-auto flex min-h-[50vh] max-w-md flex-col items-center justify-center px-4 text-center">
      <p aria-live="polite" className="text-sm text-muted-foreground">
        {status === "confirming"
          ? "Confirming your purchase..."
          : "We can't confirm yet - checking..."}
      </p>
    </div>
  );
}

export default function OrdersReturnPage() {
  return (
    <Suspense fallback={<WakingUp />}>
      <ReturnHandler />
    </Suspense>
  );
}
