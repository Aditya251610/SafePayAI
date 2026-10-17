import { z } from "zod";
import { isoString, lenientEnum } from "./common";

export const SHIPMENT_STATUSES = [
  "LABEL_CREATED",
  "IN_TRANSIT",
  "OUT_FOR_DELIVERY",
  "EXCEPTION",
  "LOST",
  "DELIVERED",
  "CANCELLED",
] as const;
export const shipmentStatusSchema = lenientEnum(SHIPMENT_STATUSES);

export const OUTCOME_PROFILES = ["ON_TIME", "LATE", "LOST", "DELIVERED_AFTER_LATE"] as const;

export const createShipmentRequestSchema = z.object({
  order_id: z.string().min(1),
  tracking_number: z.string().min(1),
  carrier_name: z.string().min(1),
  outcome_profile: z.enum(OUTCOME_PROFILES).optional(),
});
export type CreateShipmentRequest = z.infer<typeof createShipmentRequestSchema>;

export const createShipmentResponseSchema = z.object({
  id: z.string(),
  order_id: z.string(),
  status: shipmentStatusSchema,
  promised_at_sim: isoString,
  paypal_sync: z.string().nullish(),
  paypal_tracker_id: z.string().nullish(),
  simulated: z.boolean().nullish(),
  carrier_label: z.string().nullish(),
});
export type CreateShipmentResponse = z.infer<typeof createShipmentResponseSchema>;

export const shipmentSchema = z.object({
  id: z.string(),
  status: shipmentStatusSchema,
  active: z.boolean(),
  promised_at_sim: isoString,
  anomaly: z.string().nullish(),
});

export const shipmentEventSchema = z.object({
  event_id: z.string(),
  shipment_id: z.string(),
  status: shipmentStatusSchema,
  occurred_at_sim: isoString,
  note_code: z.string().nullish(),
});

export const trackingSchema = z.object({
  order_id: z.string(),
  sim_now: isoString,
  shipments: z.array(shipmentSchema),
  events: z.array(shipmentEventSchema),
  consistency: z
    .object({
      delivered: z.boolean(),
      delivered_at_sim: isoString.nullish(),
      late_detected: z.boolean(),
      lost_detected: z.boolean(),
    })
    .nullish(),
  simulated: z.boolean().nullish(),
  carrier_label: z.string().nullish(),
});
export type Tracking = z.infer<typeof trackingSchema>;

export const demoClockSchema = z.object({ sim_now: isoString });
export type DemoClock = z.infer<typeof demoClockSchema>;

const tickSchema = z.object({
  applied: z.number().int(),
  detected: z.number().int(),
  skipped_lease: z.boolean(),
});

export const advanceRequestSchema = z.object({
  delta_seconds: z.number().int(),
  reason: z.string().min(1),
});
export type AdvanceRequest = z.infer<typeof advanceRequestSchema>;

export const advanceResponseSchema = z.object({
  from_sim: isoString,
  to_sim: isoString,
  version: z.number().int(),
  tick: tickSchema.nullish(),
});
export type AdvanceResponse = z.infer<typeof advanceResponseSchema>;

export const resetRequestSchema = z.object({ reason: z.string().min(1).optional() });

export const resetResponseSchema = z.object({ offset_seconds: z.number().int() });
export type ResetResponse = z.infer<typeof resetResponseSchema>;

export const forceRequestSchema = z.object({
  to_status: z.enum(SHIPMENT_STATUSES),
  reason: z.string().min(1),
});
export type ForceRequest = z.infer<typeof forceRequestSchema>;

export const forceResponseSchema = z.object({
  id: z.string(),
  status: shipmentStatusSchema,
  source: z.string().nullish(),
  tick: tickSchema.nullish(),
});
export type ForceResponse = z.infer<typeof forceResponseSchema>;
