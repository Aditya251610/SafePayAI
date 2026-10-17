import { z } from "zod";
import { isoString, lenientEnum, protectionTermsSchema } from "./common";

export const MANDATE_STATUSES = ["active", "revoked", "expired", "exhausted"] as const;

export const merchantAllowEntrySchema = z.object({
  merchant_id: z.string().regex(/^[a-z0-9][a-z0-9_-]{0,63}$/),
  display_name: z.string().min(1).max(64),
});
export type MerchantAllowEntry = z.infer<typeof merchantAllowEntrySchema>;

/** What the buyer submits to preview. Server bounds are enforced by the server. */
export const mandateTermsInputSchema = z.object({
  currency: z.literal("USD"),
  max_total_minor: z.number().int().positive(),
  max_qty_per_line: z.number().int().min(1).nullish(),
  merchant_allowlist: z.array(merchantAllowEntrySchema).min(1).max(5),
  intent_text: z.string().trim().min(1).max(500),
  expires_at: z.string().regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/),
  protection: z.object({
    kinds_covered: z.array(z.enum(["LATE", "LOST"])).min(1),
    max_refund_minor: z.number().int().positive(),
    deliver_by_days: z.number().int().min(1).max(30),
  }),
  policy_version: z.string().nullish(),
  revoke_effect: z.string().nullish(),
});
export type MandateTermsInput = z.infer<typeof mandateTermsInputSchema>;

/** Terms as the server normalises them; sent back unchanged on sign. */
export const normalizedTermsSchema = z.object({
  currency: z.string(),
  max_total_minor: z.number().int(),
  max_qty_per_line: z.number().int(),
  merchant_allowlist: z.array(merchantAllowEntrySchema),
  intent_text: z.string(),
  expires_at: isoString,
  protection: protectionTermsSchema,
  policy_version: z.string(),
  revoke_effect: z.string(),
});
export type NormalizedTerms = z.infer<typeof normalizedTermsSchema>;

export const mandatePreviewSchema = z.object({
  normalized_terms: normalizedTermsSchema,
  screen_text: z.string(),
  screen_text_hash: z.string(),
  render_version: z.string(),
  policy_version: z.string(),
  nonce: z.string(),
  nonce_expires_at: isoString,
});
export type MandatePreview = z.infer<typeof mandatePreviewSchema>;

export const signMandateRequestSchema = z.object({
  terms: normalizedTermsSchema,
  screen_text_hash: z.string().min(1),
  nonce: z.string().min(1),
});
export type SignMandateRequest = z.infer<typeof signMandateRequestSchema>;

/** Owner view of a mandate (buyer). */
export const mandateSchema = z.object({
  mandate_id: z.string(),
  buyer_id: z.string().nullish(),
  status: lenientEnum(MANDATE_STATUSES),
  integrity: z.string(),
  schema: z.string().nullish(),
  render_version: z.string().nullish(),
  policy_version: z.string().nullish(),
  currency: z.string(),
  max_total_minor: z.number().int(),
  max_qty_per_line: z.number().int().nullish(),
  merchant_allowlist: z.array(merchantAllowEntrySchema),
  intent_text: z.string(),
  expires_at: isoString,
  protection: protectionTermsSchema,
  revoke_effect: z.string().nullish(),
  mandate_hash: z.string(),
  screen_text_hash: z.string().nullish(),
  hmac_key_id: z.string().nullish(),
  spent_minor: z.number().int(),
  reserved_minor: z.number().int(),
  remaining_minor: z.number().int(),
  created_at: isoString,
  revoked_at: isoString.nullish(),
});
export type Mandate = z.infer<typeof mandateSchema>;

/** Merchant-role view and integrity-failure view share only a few fields. */
export const mandatePublicSchema = z.object({
  mandate_id: z.string(),
  status: z.string(),
  integrity: z.string().nullish(),
  currency: z.string().nullish(),
  expires_at: isoString.nullish(),
  protection: protectionTermsSchema.nullish(),
  merchant_ids: z.array(z.string()).nullish(),
});
export type MandatePublic = z.infer<typeof mandatePublicSchema>;

export const mandateTermsViewSchema = z.object({
  mandate_id: z.string(),
  mandate_hash: z.string(),
  terms_hash: z.string(),
  mandate_status: z.string(),
  integrity: z.string(),
  protection: protectionTermsSchema,
  revoke_effect: z.string(),
  policy_version: z.string(),
  currency: z.string(),
});
export type MandateTermsView = z.infer<typeof mandateTermsViewSchema>;

export const revokeRequestSchema = z.object({ reason_code: z.string().min(1) });
export type RevokeRequest = z.infer<typeof revokeRequestSchema>;

export const revokeResponseSchema = z.object({
  mandate_id: z.string().nullish(),
  status: z.string(),
  revoked: z.boolean().nullish(),
  revoked_at: isoString.nullish(),
  released_reservations: z.number().int().nullish(),
  revoke_effect: z.string().nullish(),
  earned_protection_unchanged: z.boolean().nullish(),
  message_code: z.string().nullish(),
});
export type RevokeResponse = z.infer<typeof revokeResponseSchema>;
