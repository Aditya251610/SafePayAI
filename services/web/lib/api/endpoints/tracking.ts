import type { ApiClient } from "../client";
import { requireUuid } from "../ids";
import {
  advanceRequestSchema,
  advanceResponseSchema,
  createShipmentRequestSchema,
  createShipmentResponseSchema,
  demoClockSchema,
  forceRequestSchema,
  forceResponseSchema,
  resetRequestSchema,
  resetResponseSchema,
  trackingSchema,
  type AdvanceRequest,
  type CreateShipmentRequest,
  type ForceRequest,
} from "../schemas/tracking";
import { parseBody } from "./validate";

interface KeyOpts {
  idempotencyKey?: string;
  signal?: AbortSignal;
}

export function trackingApi(c: ApiClient) {
  return {
    createShipment: async (input: CreateShipmentRequest, opts: KeyOpts = {}) =>
      c.send("/tracking/shipments", createShipmentResponseSchema, {
        body: parseBody(createShipmentRequestSchema, input),
        idempotent: true,
        idempotencyKey: opts.idempotencyKey,
        signal: opts.signal,
      }),
    /** Always 200; an order without shipments returns empty arrays. */
    forOrder: async (orderId: string, signal?: AbortSignal) =>
      c.get(`/tracking/shipments/${requireUuid(orderId, "order id")}`, trackingSchema, { signal }),
    /** Demo-only routes. Call them only when ops status reports demo_mode. */
    demoClock: async (signal?: AbortSignal) =>
      c.get("/tracking/demo/clock", demoClockSchema, { signal }),
    advanceClock: async (input: AdvanceRequest, opts: KeyOpts = {}) =>
      c.send("/tracking/demo/clock/advance", advanceResponseSchema, {
        body: parseBody(advanceRequestSchema, input),
        idempotent: true,
        idempotencyKey: opts.idempotencyKey,
        signal: opts.signal,
      }),
    resetClock: async (reason?: string, signal?: AbortSignal) =>
      c.send("/tracking/demo/clock/reset", resetResponseSchema, {
        body: parseBody(resetRequestSchema, { reason }),
        signal,
      }),
    forceShipment: async (shipmentId: string, input: ForceRequest, signal?: AbortSignal) =>
      c.send(
        `/tracking/demo/shipments/${requireUuid(shipmentId, "shipment id")}/force`,
        forceResponseSchema,
        { body: parseBody(forceRequestSchema, input), signal },
      ),
  };
}
