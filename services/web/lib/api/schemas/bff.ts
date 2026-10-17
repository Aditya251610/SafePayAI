import { z } from "zod";
import { caseListItemSchema } from "./common";
import { mandateSchema } from "./mandate";
import { orderSchema } from "./checkout";
import { trackingSchema } from "./tracking";

export const buyerHomeSchema = z.object({
  mandates: z.array(mandateSchema),
  latest_order: orderSchema.nullish(),
  active_case: caseListItemSchema.nullish(),
});
export type BuyerHome = z.infer<typeof buyerHomeSchema>;

export const bffOrderSchema = z.object({
  order: orderSchema,
  shipment: trackingSchema.nullish(),
  case: caseListItemSchema.nullish(),
  audit_verified: z.boolean().nullish(),
});
export type BffOrder = z.infer<typeof bffOrderSchema>;

export const merchantQueueSchema = z.object({
  cases: z.array(caseListItemSchema),
  tracking_pending: z.number().int().nullish(),
});
export type MerchantQueue = z.infer<typeof merchantQueueSchema>;
