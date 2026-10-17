import { z } from "zod";
import {
  caseKindSchema,
  caseListItemSchema,
  caseStateSchema,
  isoString,
  lenientEnum,
} from "./common";

export const OFFER_ACTIONS = ["REFUND", "RESHIP"] as const;
export const OFFER_TIERS = ["AUTO", "CONFIRM", "APPROVE", "REVIEW"] as const;
export const REFUND_STATUSES = [
  "NONE",
  "REQUESTED",
  "SENT",
  "COMPLETED",
  "FAILED",
  "UNKNOWN",
  "NOT_SENT",
] as const;
export const EXECUTIONS = ["DONE", "IN_PROGRESS", "QUEUED_FROZEN", "NOT_STARTED"] as const;
export const DECLINE_REASONS = ["NOT_WANTED", "WANT_HUMAN", "OTHER"] as const;
export const MERCHANT_ACTIONS = ["OVERRIDE_OFFER", "CONFIRM_RESHIP"] as const;

export const offerSchema = z.object({
  offer_id: z.string(),
  action: lenientEnum(OFFER_ACTIONS),
  amount_minor: z.number().int(),
  currency: z.string(),
  tier: lenientEnum(OFFER_TIERS),
  status: z.string(),
  proposal_hash: z.string(),
  expires_at: z.string().nullish(),
});
export type Offer = z.infer<typeof offerSchema>;

export const reportCaseRequestSchema = z.object({
  order_id: z.string().min(1),
  text: z.string().trim().min(1).max(4000),
});
export type ReportCaseRequest = z.infer<typeof reportCaseRequestSchema>;

export const reportCaseResponseSchema = z.object({
  case_id: z.string(),
  state: caseStateSchema,
  kind: caseKindSchema,
  origin: z.string(),
  reasons: z.array(z.object({ code: z.string(), text: z.string().nullish() })).nullish(),
  offer: offerSchema.nullish(),
  protection: z.record(z.unknown()).nullish(),
});
export type ReportCaseResponse = z.infer<typeof reportCaseResponseSchema>;

export const caseDetailSchema = z.object({
  case_id: z.string(),
  order_id: z.string(),
  state: caseStateSchema,
  version: z.number().int().nullish(),
  kind: caseKindSchema,
  origin: z.string(),
  opened_at: isoString,
  window_hold: z.boolean().nullish(),
  timeline: z
    .array(
      z.object({
        from: z.string().nullish(),
        to: z.string(),
        actor: z.string().nullish(),
        reason: z.string().nullish(),
        at: isoString,
      }),
    )
    .nullish(),
  decision: z
    .object({
      class: z.string(),
      policy_version: z.string().nullish(),
      reasons: z.array(z.unknown()).nullish(),
      illustrative: z.boolean().nullish(),
    })
    .nullish(),
  offer: offerSchema.nullish(),
  refund: z.object({ status: z.string(), paypal_refund_id: z.string().nullish() }).nullish(),
  queued_reason: z.string().nullish(),
});
export type CaseDetail = z.infer<typeof caseDetailSchema>;

export const caseListSchema = z.object({ items: z.array(caseListItemSchema) });
export type CaseList = z.infer<typeof caseListSchema>;

export const reviewQueueSchema = z.object({
  items: z.array(
    z.object({
      case_id: z.string(),
      kind: caseKindSchema,
      reason_codes: z.array(z.string()),
      entered_at: isoString,
      age_s: z.number(),
      sla_target_s: z.number().nullish(),
      sla_state: z.string(),
      brief: z.string(),
    }),
  ),
});
export type ReviewQueue = z.infer<typeof reviewQueueSchema>;

export const acceptOfferRequestSchema = z.object({ proposal_hash: z.string().min(1) });

export const acceptOfferResponseSchema = z.object({
  case_id: z.string(),
  state: caseStateSchema,
  execution: lenientEnum(EXECUTIONS),
  refund: z.object({ status: z.string(), paypal_refund_id: z.string().nullish() }).nullish(),
});
export type AcceptOfferResponse = z.infer<typeof acceptOfferResponseSchema>;

export const declineOfferRequestSchema = z.object({ reason_code: z.enum(DECLINE_REASONS) });

export const declineOfferResponseSchema = z.object({ state: caseStateSchema });
export type DeclineOfferResponse = z.infer<typeof declineOfferResponseSchema>;

export const approvalPreviewSchema = z.object({
  case_id: z.string(),
  action: lenientEnum(OFFER_ACTIONS),
  amount_minor: z.number().int(),
  currency: z.string(),
  summary: z.string(),
  expires_at: z.string().nullish(),
  proposal_hash: z.string(),
});
export type ApprovalPreview = z.infer<typeof approvalPreviewSchema>;

export const consentRequestSchema = z.object({
  proposal_hash: z.string().min(1),
  csrf_nonce: z.string().min(1),
});

export const consentResponseSchema = z.object({
  case_id: z.string(),
  state: caseStateSchema,
  execution: lenientEnum(EXECUTIONS),
});
export type ConsentResponse = z.infer<typeof consentResponseSchema>;

export const merchantActionRequestSchema = z.object({ type: z.enum(MERCHANT_ACTIONS) });

export const merchantActionResponseSchema = z.object({
  case_id: z.string(),
  state: caseStateSchema,
  offer_id: z.string().nullish(),
  supersedes: z.string().nullish(),
});
export type MerchantActionResponse = z.infer<typeof merchantActionResponseSchema>;

export const refundsFrozenStateSchema = z.object({
  refunds_frozen: z.boolean(),
  reason: z.string().nullish(),
  set_by: z.string().nullish(),
  set_at: z.string().nullish(),
  epoch: z.number().int().nullish(),
  adapter_mirror: z.string().nullish(),
  readable: z.boolean().nullish(),
});
export type RefundsFrozenState = z.infer<typeof refundsFrozenStateSchema>;
