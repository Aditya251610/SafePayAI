"use client";

import { AppShell } from "@/components/shell/app-shell";
import { RequireRole } from "@/components/shared/require-role";
import { useSession } from "@/lib/auth/session";

/** For screens every signed-in role may open, such as the audit log. */
export function AnyRoleShell({ children }: { children: React.ReactNode }) {
  return (
    <RequireRole roles="any">
      <Framed>{children}</Framed>
    </RequireRole>
  );
}

function Framed({ children }: { children: React.ReactNode }) {
  const { session } = useSession();
  // RequireRole renders children only for an authenticated session.
  const role = session.status === "authenticated" ? session.role : "buyer";
  return <AppShell role={role}>{children}</AppShell>;
}
