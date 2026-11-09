import type { Role } from "../api/schemas/common";
import type { DemoPersona } from "../api/schemas/auth";

/** Picker groups, in the order they are shown. */
export const PERSONA_GROUPS: readonly { role: Role; label: string }[] = [
  { role: "buyer", label: "Buyer" },
  { role: "merchant", label: "Merchant" },
  { role: "operator", label: "Operator" },
  { role: "reviewer", label: "Reviewer" },
];

const OPERATOR_BLURB = "Moves the simulated carrier clock and holds the refund kill switch";
const REVIEWER_BLURB = "Decides cases the rules hand to a person";

const BLURB_BY_HANDLE: Record<string, string> = {
  "buyer-persona": "A buyer with a signed mandate, four orders, a refund and open cases",
  "buyer-alex": "A buyer with nothing yet - start from scratch",
  "reviewer-demo": REVIEWER_BLURB,
  operator: OPERATOR_BLURB,
};

const BLURB_BY_ROLE: Record<Role, string> = {
  buyer: "A seeded buyer account",
  merchant: "Ships that merchant's orders on the simulated carrier",
  operator: OPERATOR_BLURB,
  reviewer: REVIEWER_BLURB,
};

/** One line on what the account shows. Unknown handles fall back to the role's line. */
export function personaBlurb(p: Pick<DemoPersona, "handle" | "role">): string {
  return BLURB_BY_HANDLE[p.handle] ?? BLURB_BY_ROLE[p.role];
}

export function personaName(p: Pick<DemoPersona, "handle" | "display_name">): string {
  return p.display_name?.trim() || p.handle;
}

/** Split personas into the picker's groups, dropping empty ones. */
export function groupPersonas(personas: readonly DemoPersona[]) {
  return PERSONA_GROUPS.map((g) => ({
    ...g,
    items: personas.filter((p) => p.role === g.role),
  })).filter((g) => g.items.length > 0);
}
