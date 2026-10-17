import type { ApiClient } from "../client";
import { pathSegment, requireUuid } from "../ids";
import {
  acceptOfferRequestSchema,
  acceptOfferResponseSchema,
  approvalPreviewSchema,
  caseDetailSchema,
  caseListSchema,
  consentRequestSchema,
  consentResponseSchema,
  declineOfferRequestSchema,
  declineOfferResponseSchema,
  merchantActionRequestSchema,
  merchantActionResponseSchema,
  refundsFrozenStateSchema,
  reportCaseRequestSchema,
  reportCaseResponseSchema,
  reviewQueueSchema,
  type ReportCaseRequest,
} from "../schemas/resolution";
import { parseBody } from "./validate";

interface KeyOpts {
  idempotencyKey?: string;
  signal?: AbortSignal;
}

export function resolutionApi(c: ApiClient) {
  return {
    report: async (input: ReportCaseRequest, opts: KeyOpts = {}) =>
      c.send("/resolution/cases/report", reportCaseResponseSchema, {
        body: parseBody(reportCaseRequestSchema, input),
        idempotent: true,
        idempotencyKey: opts.idempotencyKey,
        signal: opts.signal,
      }),
    case: async (caseId: string, signal?: AbortSignal) =>
      c.get(`/resolution/cases/${requireUuid(caseId, "case id")}`, caseDetailSchema, { signal }),
    /** Merchant and operator only. */
    cases: async (query: { orderId?: string } = {}, signal?: AbortSignal) =>
      c.get("/resolution/cases", caseListSchema, {
        query: { order_id: query.orderId ? requireUuid(query.orderId, "order id") : undefined },
        signal,
      }),
    /** Reviewer only; read-only in this build. */
    reviewQueue: async (signal?: AbortSignal) =>
      c.get("/resolution/review/queue", reviewQueueSchema, { signal }),
    /** Money route. */
    acceptOffer: async (offerId: string, proposalHash: string, opts: KeyOpts = {}) =>
      c.send(
        `/resolution/offers/${requireUuid(offerId, "offer id")}/accept`,
        acceptOfferResponseSchema,
        {
          body: parseBody(acceptOfferRequestSchema, { proposal_hash: proposalHash }),
          idempotent: true,
          idempotencyKey: opts.idempotencyKey,
          money: true,
          signal: opts.signal,
        },
      ),
    declineOffer: async (
      offerId: string,
      reasonCode: "NOT_WANTED" | "WANT_HUMAN" | "OTHER",
      opts: KeyOpts = {},
    ) =>
      c.send(
        `/resolution/offers/${requireUuid(offerId, "offer id")}/decline`,
        declineOfferResponseSchema,
        {
          body: parseBody(declineOfferRequestSchema, { reason_code: reasonCode }),
          idempotent: true,
          idempotencyKey: opts.idempotencyKey,
          signal: opts.signal,
        },
      ),
    approvalPreview: async (token: string, signal?: AbortSignal) =>
      c.get(
        `/resolution/approvals/${pathSegment(token, "approval token")}`,
        approvalPreviewSchema,
        {
          signal,
        },
      ),
    /** Money route. */
    consent: async (
      token: string,
      input: { proposalHash: string; csrfNonce: string },
      opts: KeyOpts = {},
    ) =>
      c.send(
        `/resolution/approvals/${pathSegment(token, "approval token")}/consent`,
        consentResponseSchema,
        {
          body: parseBody(consentRequestSchema, {
            proposal_hash: input.proposalHash,
            csrf_nonce: input.csrfNonce,
          }),
          idempotent: true,
          idempotencyKey: opts.idempotencyKey,
          money: true,
          signal: opts.signal,
        },
      ),
    merchantAction: async (
      caseId: string,
      type: "OVERRIDE_OFFER" | "CONFIRM_RESHIP",
      opts: KeyOpts = {},
    ) =>
      c.send(
        `/resolution/cases/${requireUuid(caseId, "case id")}/merchant-action`,
        merchantActionResponseSchema,
        {
          body: parseBody(merchantActionRequestSchema, { type }),
          idempotent: true,
          idempotencyKey: opts.idempotencyKey,
          signal: opts.signal,
        },
      ),
    refundsFrozen: async (signal?: AbortSignal) =>
      c.get("/resolution/controls/refunds-frozen", refundsFrozenStateSchema, { signal }),
  };
}
