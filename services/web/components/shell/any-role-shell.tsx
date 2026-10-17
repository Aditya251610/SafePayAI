"use client";

import { AppShell } from "@/components/shell/app-shell";
import { RequireRole } from "@/components/shared/require-role";
import { Notice } from "@/components/ui/notice";
import type { Role } from "@/lib/api/schemas/common";
import { useSession } from "@/lib/auth/session";

function Framed({ children, desktopOnly }: { children: React.ReactNode; desktopOnly: boolean }) {
  const { session } = useSession();
  // RequireRole renders children only for an authenticated session.
  const role = session.status === "authenticated" ? session.role : "buyer";
  return (
    <AppShell role={role}>
      {desktopOnly && (
        <div className="py-10 md:hidden">
          <Notice tone="info" title="Use a larger screen">
            This staff screen is built for a tablet or desktop. Open it on a wider display to work
            in it.
          </Notice>
        </div>
      )}
      <div className={desktopOnly ? "hidden md:block" : undefined}>{children}</div>
    </AppShell>
  );
}

/**
 * Frame for screens outside the buyer area. `roles` is a convenience gate;
 * the gateway decides. Staff screens set `desktopOnly` because they have no
 * phone layout.
 */
export function RoleShell({
  roles,
  desktopOnly = false,
  children,
}: {
  roles: readonly Role[] | "any";
  desktopOnly?: boolean;
  children: React.ReactNode;
}) {
  return (
    <RequireRole roles={roles}>
      <Framed desktopOnly={desktopOnly}>{children}</Framed>
    </RequireRole>
  );
}

/** For screens every signed-in role may open, such as the audit log. */
export function AnyRoleShell({ children }: { children: React.ReactNode }) {
  return <RoleShell roles="any">{children}</RoleShell>;
}
