import { z } from "zod";
import { checkSchema, isoString, lenientEnum } from "./common";

export const CART_STATUSES = ["CHECKED", "NEEDS_CONFIRMATION", "BLOCKED"] as const;

export const ORDER_STATUSES = [
  "CREATING",
  "CREATE_UNKNOWN",
  "CREATE_FAILED",
  "AWAITING_APPROVAL",
  "APPROVED",
  "CAPTURE_PENDING",
  "CAPTURE_UNKNOWN",
  "CAPTURED",
  "CAPTURE_FAILED",
  "CANCELLED_REVOKED",
  "CANCELLED_BUYER",
  "EXPIRED",
] as const;

/** Orders in these states will not change again without a new action. */
export const TERMINAL_ORDER_STATUSES: ReadonlySet<string> = new Set([
  "CAPTURED",
  "CAPTURE_FAILED",
  "CANCELLED_REVOKED",
  "CANCELLED_BUYER",
  "CREATE_FAILED",
  "EXPIRED",
]);

export const createCartRequestSchema = z.object({
  mandate_id: z.string().min(1),
  lines: z.array(z.object({ sku: z.string().min(1), qty: z.number().int().min(1) })).min(1),
  proposal_id: z.string().nullish(),
});
export type CreateCartRequest = z.infer<typeof createCartRequestSchema>;

export const cartLineSchema = z.object({
  sku: z.string(),
  qty: z.number().int(),
  unit_minor: z.number().int(),
  line_minor: z.number().int(),
  merchant_id: z.string(),
});

export const cartSchema = z.object({
  cart_id: z.string(),
  status: lenientEnum(CART_STATUSES),
  currency: z.string(),
  lines: z.array(cartLineSchema),
  total_minor: z.number().int(),
  remaining_cap_minor_after: z.number().int().nullish(),
  proposal_hash: z.string(),
  checks: z.array(checkSchema),
  intent_fit: z
    .object({
      verdict: z.string(),
      reason_code: z.string().nullish(),
      advisory: z.boolean().nullish(),
    })
    .nullish(),
  expires_at: isoString.nullish(),
});
export type Cart = z.infer<typeof cartSchema>;

export const confirmCartRequestSchema = z.object({
  proposal_hash: z.string().min(1),
  confirm_intent_fit: z.boolean().optional(),
});
export type ConfirmCartRequest = z.infer<typeof confirmCartRequestSchema>;

export const confirmCartResponseSchema = z.object({
  order_id: z.string(),
  status: lenientEnum(ORDER_STATUSES),
  approve_url: z.string(),
  total_minor: z.number().int(),
  currency: z.string(),
  expires_at: isoString.nullish(),
});
export type ConfirmCartResponse = z.infer<typeof confirmCartResponseSchema>;

export const orderSchema = z.object({
  order_id: z.string(),
  cart_id: z.string().nullish(),
  buyer_id: z.string().nullish(),
  mandate_id: z.string(),
  status: lenientEnum(ORDER_STATUSES),
  total_minor: z.number().int(),
  currency: z.string(),
  paypal_order_id: z.string().nullish(),
  approve_url: z.string().nullish(),
  failure_code: z.string().nullish(),
  created_at: isoString,
  updated_at: isoString.nullish(),
  capture_id: z.string().nullish(),
  capture_status: z.string().nullish(),
  mandate_reservation_id: z.string().nullish(),
  item_titles: z.array(z.string()).nullish(),
});
export type Order = z.infer<typeof orderSchema>;

export const orderListSchema = z.object({ items: z.array(orderSchema) });
export type OrderList = z.infer<typeof orderListSchema>;

export const receiptSchema = z.object({
  order_id: z.string(),
  paypal_order_id: z.string().nullish(),
  capture_id: z.string().nullish(),
  status: z.string(),
  amount_minor: z.number().int(),
  amount_major: z.string(),
  currency: z.string(),
  lines: z.array(
    z.object({
      sku: z.string(),
      qty: z.number().int(),
      unit_minor: z.number().int(),
      unit_major: z.string(),
      line_minor: z.number().int(),
      line_major: z.string(),
      merchant_id: z.string(),
    }),
  ),
  checks: z.array(checkSchema),
  intent_fit: z
    .object({
      verdict: z.string(),
      reason_code: z.string().nullish(),
      confidence: z.number().nullish(),
      advisory: z.boolean().nullish(),
      note: z.string().nullish(),
    })
    .nullish(),
  mandate: z.object({ mandate_id: z.string(), mandate_hash: z.string().nullish() }),
  audit: z.object({ event_id: z.string(), seq: z.number().int().nullish() }).nullish(),
  remaining_cap_minor: z.number().int().nullish(),
  protection: z.object({
    window_days: z.number().int(),
    protected_until_day: z.number().int(),
    label: z.string(),
  }),
  disclosures: z.array(z.string()),
});
export type Receipt = z.infer<typeof receiptSchema>;

export const returnRequestSchema = z.object({
  state: z.string().min(1),
  token: z.string().min(1),
  payer_id: z.string().min(1),
});
export type ReturnRequest = z.infer<typeof returnRequestSchema>;

export const returnResponseSchema = z.object({
  order_id: z.string(),
  status: z.string(),
  receipt_url: z.string().nullish(),
  message_code: z.string().nullish(),
});
export type ReturnResponse = z.infer<typeof returnResponseSchema>;

export const cancelRequestSchema = z.object({ state: z.string().min(1) });

export const cancelResponseSchema = z.object({ order_id: z.string(), status: z.string() });
export type CancelResponse = z.infer<typeof cancelResponseSchema>;
