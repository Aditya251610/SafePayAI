import type { CaseState } from "../api/schemas/common";

/** The five stages the buyer sees. The 12 backend states collapse onto these. */
export const CASE_RAIL_STEPS = [
  "Protected",
  "Problem found",
  "Offer",
  "Decision",
  "Resolved",
] as const;

const STEP_BY_STATE: Record<CaseState, number> = {
  PROTECTED: 0,
  MONITORING: 0,
  PROBLEM_DETECTED: 1,
  TRIAGED: 1,
  OFFERED: 2,
  HUMAN_REVIEW: 2,
  APPROVED: 3,
  REFUNDING: 3,
  DECLINED: 3,
  RESOLVED_REFUNDED: 4,
  RESOLVED_RESHIP: 4,
  CLOSED: 4,
};

/** Index of the current rail step; unknown states sit at the start. */
export function railStep(state: string): number {
  return (STEP_BY_STATE as Record<string, number | undefined>)[state] ?? 0;
}
