import type { ApiClient } from "../client";
import { requireUuid } from "../ids";
import { bffOrderSchema, buyerHomeSchema, merchantQueueSchema } from "../schemas/bff";

export function bffApi(c: ApiClient) {
  return {
    buyerHome: async (signal?: AbortSignal) =>
      c.get("/bff/buyer-home", buyerHomeSchema, { signal }),
    order: async (orderId: string, signal?: AbortSignal) =>
      c.get(`/bff/orders/${requireUuid(orderId, "order id")}`, bffOrderSchema, { signal }),
    /** The upstream state filter is ignored today, so callers filter on state themselves. */
    merchantQueue: async (signal?: AbortSignal) =>
      c.get("/bff/merchant-queue", merchantQueueSchema, { signal }),
  };
}
