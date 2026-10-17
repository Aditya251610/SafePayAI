import type { ApiClient } from "../client";
import { requireUuid } from "../ids";
import {
  mandatePreviewSchema,
  mandateSchema,
  mandateTermsInputSchema,
  mandateTermsViewSchema,
  revokeRequestSchema,
  revokeResponseSchema,
  signMandateRequestSchema,
  type MandateTermsInput,
  type SignMandateRequest,
} from "../schemas/mandate";
import { parseBody } from "./validate";

export function mandateApi(c: ApiClient) {
  return {
    /** First step of signing; returns the nonce and screen text hash sign needs. */
    preview: async (terms: MandateTermsInput, signal?: AbortSignal) =>
      c.send("/mandate/mandates/preview", mandatePreviewSchema, {
        body: { terms: parseBody(mandateTermsInputSchema, terms) },
        signal,
      }),
    sign: async (
      input: SignMandateRequest,
      opts: { idempotencyKey?: string; signal?: AbortSignal } = {},
    ) =>
      c.send("/mandate/mandates", mandateSchema, {
        body: parseBody(signMandateRequestSchema, input),
        idempotent: true,
        idempotencyKey: opts.idempotencyKey,
        signal: opts.signal,
      }),
    get: async (id: string, signal?: AbortSignal) =>
      c.get(`/mandate/mandates/${requireUuid(id, "mandate id")}`, mandateSchema, { signal }),
    terms: async (id: string, signal?: AbortSignal) =>
      c.get(`/mandate/mandates/${requireUuid(id, "mandate id")}/terms`, mandateTermsViewSchema, {
        signal,
      }),
    revoke: async (id: string, reasonCode = "BUYER_REQUEST", signal?: AbortSignal) =>
      c.send(`/mandate/mandates/${requireUuid(id, "mandate id")}/revoke`, revokeResponseSchema, {
        body: parseBody(revokeRequestSchema, { reason_code: reasonCode }),
        signal,
      }),
  };
}
