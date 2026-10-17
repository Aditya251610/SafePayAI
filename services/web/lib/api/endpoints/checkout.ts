import type { ApiClient } from "../client";
import { requireUuid } from "../ids";
import {
  cancelRequestSchema,
  cancelResponseSchema,
  cartSchema,
  confirmCartRequestSchema,
  confirmCartResponseSchema,
  createCartRequestSchema,
  orderListSchema,
  orderSchema,
  receiptSchema,
  returnRequestSchema,
  returnResponseSchema,
  type ConfirmCartRequest,
  type CreateCartRequest,
  type ReturnRequest,
} from "../schemas/checkout";
import { parseBody } from "./validate";

interface KeyOpts {
  idempotencyKey?: string;
  signal?: AbortSignal;
}

export function checkoutApi(c: ApiClient) {
  return {
    createCart: async (input: CreateCartRequest, opts: KeyOpts = {}) =>
      c.send("/checkout/carts", cartSchema, {
        body: parseBody(createCartRequestSchema, input),
        idempotent: true,
        idempotencyKey: opts.idempotencyKey,
        signal: opts.signal,
      }),
    /** Money route. A 504 surfaces as AmbiguousOutcomeError; read the order, don't retry. */
    confirmCart: async (cartId: string, input: ConfirmCartRequest, opts: KeyOpts = {}) =>
      c.send(
        `/checkout/carts/${requireUuid(cartId, "cart id")}/confirm`,
        confirmCartResponseSchema,
        {
          body: parseBody(confirmCartRequestSchema, input),
          idempotent: true,
          idempotencyKey: opts.idempotencyKey,
          money: true,
          signal: opts.signal,
        },
      ),
    /** Money route and the manual-completion path when the PayPal return never arrives. */
    capture: async (orderId: string, opts: KeyOpts = {}) =>
      c.send(`/checkout/orders/${requireUuid(orderId, "order id")}/capture`, orderSchema, {
        body: {},
        idempotent: true,
        idempotencyKey: opts.idempotencyKey,
        money: true,
        signal: opts.signal,
      }),
    order: async (orderId: string, signal?: AbortSignal) =>
      c.get(`/checkout/orders/${requireUuid(orderId, "order id")}`, orderSchema, { signal }),
    receipt: async (orderId: string, signal?: AbortSignal) =>
      c.get(`/checkout/orders/${requireUuid(orderId, "order id")}/receipt`, receiptSchema, {
        signal,
      }),
    /** Buyers may omit mandateId; merchants and operators must pass it. */
    orders: async (
      query: { mandateId?: string; status?: string; limit?: number } = {},
      signal?: AbortSignal,
    ) =>
      c.get("/checkout/orders", orderListSchema, {
        query: {
          mandate_id: query.mandateId ? requireUuid(query.mandateId, "mandate id") : undefined,
          status: query.status,
          limit: query.limit,
        },
        signal,
      }),
    completeReturn: async (input: ReturnRequest, signal?: AbortSignal) =>
      c.send("/checkout/orders/return", returnResponseSchema, {
        body: parseBody(returnRequestSchema, input),
        signal,
      }),
    cancelReturn: async (state: string, signal?: AbortSignal) =>
      c.send("/checkout/orders/cancel", cancelResponseSchema, {
        body: parseBody(cancelRequestSchema, { state }),
        signal,
      }),
  };
}
