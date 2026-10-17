"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { WakingUp } from "@/components/shared/waking-up";
import type { Role } from "@/lib/api/schemas/common";
import { homeFor } from "@/lib/auth/roles";
import { useSession } from "@/lib/auth/session";

/**
 * Convenience gate. The gateway still decides; this only avoids showing the
 * wrong screen. Anonymous visitors go to /login and come back afterwards.
 */
export function RequireRole({
  roles,
  children,
}: {
  roles: readonly Role[] | "any";
  children: React.ReactNode;
}) {
  const { session, refresh } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  React.useEffect(() => {
    if (session.status === "anonymous") {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [session.status, router, pathname]);

  if (session.status === "loading" || session.status === "anonymous") {
    return (
      <div className="mx-auto max-w-page px-4 py-12" aria-busy="true">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="mt-6 h-40 w-full" />
      </div>
    );
  }

  if (session.status === "error") {
    return session.waking ? (
      <WakingUp />
    ) : (
      <div className="mx-auto max-w-lg px-4 py-12">
        <Notice tone="warn" title="Could not load your session">
          {session.error.message}
        </Notice>
        <Button className="mt-4" variant="secondary" onClick={() => void refresh()}>
          Try again
        </Button>
      </div>
    );
  }

  if (roles !== "any" && !roles.includes(session.role)) {
    return (
      <div className="mx-auto max-w-lg px-4 py-12">
        <Notice tone="warn" title="Wrong account type">
          This page is for a different kind of account. You are signed in as {session.role}.
        </Notice>
        <Button asChild className="mt-4">
          <Link href={homeFor(session.role)}>Go to your home</Link>
        </Button>
      </div>
    );
  }

  return <>{children}</>;
}
