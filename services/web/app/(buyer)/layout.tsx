"use client";

import { AppShell } from "@/components/shell/app-shell";
import { RequireRole } from "@/components/shared/require-role";

/** Role check here is convenience only; the gateway is authoritative. */
export default function BuyerLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireRole roles={["buyer"]}>
      <AppShell role="buyer">{children}</AppShell>
    </RequireRole>
  );
}
