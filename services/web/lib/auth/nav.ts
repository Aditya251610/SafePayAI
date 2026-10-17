import type { Role } from "../api/schemas/common";

export interface NavItem {
  href: string;
  label: string;
  /** Short label for the mobile tab bar. */
  tab: string;
}

/** Navigation per role. Buyers get four bottom tabs on phones. */
export const NAV: Readonly<Record<Role, readonly NavItem[]>> = {
  buyer: [
    { href: "/home", label: "Home", tab: "Home" },
    { href: "/intent", label: "Shop", tab: "Shop" },
    { href: "/orders", label: "Orders", tab: "Orders" },
    { href: "/mandate/new", label: "Mandate", tab: "Mandate" },
  ],
  merchant: [
    { href: "/merchant", label: "Queue", tab: "Queue" },
    { href: "/audit", label: "Audit log", tab: "Audit" },
  ],
  operator: [
    { href: "/ops", label: "Controls", tab: "Ops" },
    { href: "/merchant", label: "Queue", tab: "Queue" },
    { href: "/audit", label: "Audit log", tab: "Audit" },
  ],
  reviewer: [
    { href: "/review", label: "Review", tab: "Review" },
    { href: "/audit", label: "Audit log", tab: "Audit" },
  ],
};

export function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}
