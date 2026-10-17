import type { Role } from "../api/schemas/common";

/** Where each role lands after sign-in. */
export const ROLE_HOME: Readonly<Record<Role, string>> = {
  buyer: "/home",
  merchant: "/merchant",
  operator: "/ops",
  reviewer: "/review",
};

export function homeFor(role: Role): string {
  return ROLE_HOME[role];
}

interface RouteRule {
  prefix: string;
  roles: readonly Role[] | "any";
}

/**
 * Convenience only. The gateway is authoritative and answers 403 on its own;
 * this table lets the UI avoid a flash of the wrong screen.
 */
const RULES: readonly RouteRule[] = [
  { prefix: "/home", roles: ["buyer"] },
  { prefix: "/mandate", roles: ["buyer"] },
  { prefix: "/intent", roles: ["buyer"] },
  { prefix: "/agent", roles: ["buyer"] },
  { prefix: "/cart", roles: ["buyer"] },
  { prefix: "/checkout", roles: ["buyer"] },
  { prefix: "/orders", roles: ["buyer"] },
  { prefix: "/cases", roles: ["buyer"] },
  { prefix: "/approve", roles: ["buyer"] },
  { prefix: "/audit", roles: "any" },
  { prefix: "/merchant", roles: ["merchant", "operator"] },
  { prefix: "/ops", roles: ["operator"] },
  { prefix: "/review", roles: ["reviewer"] },
];

function matches(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

/** Routes with no rule (landing, login) are open. */
export function canAccess(role: Role, pathname: string): boolean {
  const rule = RULES.find((r) => matches(pathname, r.prefix));
  if (!rule) return true;
  return rule.roles === "any" || rule.roles.includes(role);
}

/** Accept only same-origin relative paths for post-login redirects. */
export function safeNextPath(next: string | null | undefined, fallback: string): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) {
    return fallback;
  }
  return next;
}

/** True when `url` is https and its host is on the allowlist (PayPal approve redirect guard). */
export function isAllowedApproveUrl(url: string, allowedHosts: readonly string[]): boolean {
  try {
    const u = new URL(url);
    return u.protocol === "https:" && allowedHosts.includes(u.hostname);
  } catch {
    return false;
  }
}
