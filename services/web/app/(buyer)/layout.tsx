"use client";

import { AppShell } from "@/components/shell/app-shell";
import { RequireRole } from "@/components/shared/require-role";
import { WakePing } from "@/components/shared/wake-ping";

/** Role check here is convenience only; the gateway is authoritative. */
export default function BuyerLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireRole roles={["buyer"]}>
      <WakePing />
      <AppShell role="buyer">{children}</AppShell>
    </RequireRole>
  );
}
