"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { Logo } from "@/components/brand/logo";
import { Tag } from "@/components/ui/tag";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/shared/theme-toggle";
import type { Role } from "@/lib/api/schemas/common";
import { NAV, isActive } from "@/lib/auth/nav";
import { useSession } from "@/lib/auth/session";
import { cn } from "@/lib/utils";

/**
 * Responsive frame for signed-in screens:
 * phone: bottom tabs; tablet: 72 px icon rail; desktop: top nav.
 */
export function AppShell({ role, children }: { role: Role; children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { session, signOut } = useSession();
  const items = NAV[role];
  const name = session.status === "authenticated" ? (session.me.display_name ?? role) : role;

  async function handleSignOut() {
    await signOut();
    router.replace("/");
  }

  return (
    <div className="md:pl-[72px] lg:pl-0">
      <header className="mx-auto hidden max-w-page items-center justify-between gap-4 border-b-2 border-line px-10 py-6 lg:flex">
        <div className="flex items-center gap-8">
          <Link href="/" aria-label="SafePayAI home">
            <Logo />
          </Link>
          <nav aria-label="Main" className="flex gap-6">
            {items.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive(pathname, item.href) ? "page" : undefined}
                className={cn(
                  "border-b-4 pb-1.5 text-xs font-bold uppercase tracking-[0.12em]",
                  isActive(pathname, item.href)
                    ? "border-fg text-fg"
                    : "border-transparent text-dim hover:text-fg",
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-3">
          <Tag tone="dashed">Sandbox · test funds</Tag>
          <span className="text-sm text-mute">{name}</span>
          <ThemeToggle />
          <Button variant="secondary" size="sm" onClick={() => void handleSignOut()}>
            Sign out
          </Button>
        </div>
      </header>

      <div className="flex items-center justify-between gap-3 border-b-2 border-line px-4 py-3 lg:hidden">
        <Link href="/" aria-label="SafePayAI home">
          <Logo size={24} />
        </Link>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Button variant="secondary" size="sm" onClick={() => void handleSignOut()}>
            Sign out
          </Button>
        </div>
      </div>

      <nav
        aria-label="Main"
        className="fixed inset-y-0 left-0 z-30 hidden w-[72px] flex-col items-center gap-2 border-r-2 border-line bg-panel py-4 md:flex lg:hidden"
      >
        {items.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            aria-label={item.label}
            aria-current={isActive(pathname, item.href) ? "page" : undefined}
            className={cn(
              "flex h-14 w-14 items-center justify-center border-2 text-[10px] font-bold uppercase tracking-[0.06em]",
              isActive(pathname, item.href)
                ? "border-fg text-fg"
                : "border-transparent text-dim hover:text-fg",
            )}
          >
            {item.tab}
          </Link>
        ))}
      </nav>

      <div className="mx-auto max-w-page px-4 pb-24 md:px-8 md:pb-12 lg:px-10">{children}</div>

      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-30 flex border-t-2 border-line bg-panel pb-[env(safe-area-inset-bottom,0px)] md:hidden"
      >
        {items.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            aria-current={isActive(pathname, item.href) ? "page" : undefined}
            className={cn(
              "flex min-h-12 flex-1 items-center justify-center border-t-4 text-[11px] font-bold uppercase tracking-[0.08em]",
              isActive(pathname, item.href) ? "border-fg text-fg" : "border-transparent text-dim",
            )}
          >
            {item.tab}
          </Link>
        ))}
      </nav>
    </div>
  );
}
