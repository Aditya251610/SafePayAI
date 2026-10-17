import { z } from "zod";

/**
 * Enums come from the services' code, which can gain members later. The
 * schema therefore accepts any string and the type keeps the known members
 * for autocomplete and exhaustive-looking switches with a default branch.
 */
export function lenientEnum<const T extends readonly string[]>(
  _known: T,
): z.ZodType<T[number] | (string & Record<never, never>)> {
  return z.string();
}

export const isoString = z.string().min(1);

export const ROLES = ["buyer", "merchant", "operator", "reviewer"] as const;
export type Role = (typeof ROLES)[number];
export const roleSchema = z.enum(ROLES);

export const CASE_STATES = [
  "PROTECTED",
  "MONITORING",
  "PROBLEM_DETECTED",
  "TRIAGED",
  "OFFERED",
  "HUMAN_REVIEW",
  "APPROVED",
  "REFUNDING",
  "RESOLVED_REFUNDED",
  "RESOLVED_RESHIP",
  "DECLINED",
  "CLOSED",
] as const;
export type CaseState = (typeof CASE_STATES)[number];
export const caseStateSchema = lenientEnum(CASE_STATES);

export const CASE_KINDS = [
  "LATE",
  "LOST",
  "DAMAGED",
  "WRONG_ITEM",
  "NOT_AS_DESCRIBED",
  "OTHER",
] as const;
export const caseKindSchema = lenientEnum(CASE_KINDS);

export const CHECK_RESULTS = ["PASS", "BLOCK", "TIGHTEN", "SKIPPED"] as const;

export const checkSchema = z.object({
  name: z.string(),
  result: lenientEnum(CHECK_RESULTS),
  reason_code: z.string().nullish(),
  source: z.string().nullish(),
  advisory: z.boolean().nullish(),
  detail: z.string().nullish(),
});
export type Check = z.infer<typeof checkSchema>;

export const protectionTermsSchema = z.object({
  kinds_covered: z.array(z.string()),
  max_refund_minor: z.number().int(),
  deliver_by_days: z.number().int(),
});
export type ProtectionTerms = z.infer<typeof protectionTermsSchema>;

/** Case summary as returned by list endpoints and the BFF. */
export const caseListItemSchema = z.object({
  case_id: z.string(),
  order_id: z.string(),
  state: caseStateSchema,
  kind: caseKindSchema,
  origin: z.string(),
  opened_at: isoString,
});
export type CaseListItem = z.infer<typeof caseListItemSchema>;
