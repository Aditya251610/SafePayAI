import type { ApiClient } from "../client";
import { pathSegment } from "../ids";
import { catalogItemDetailSchema, catalogListSchema } from "../schemas/catalog";

export function catalogApi(c: ApiClient) {
  return {
    items: async (
      query: { merchant_id?: string; category_id?: string; limit?: number; offset?: number } = {},
      signal?: AbortSignal,
    ) => c.get("/catalog/items", catalogListSchema, { query, signal }),
    item: async (sku: string, signal?: AbortSignal) =>
      c.get(`/catalog/items/${pathSegment(sku, "sku")}`, catalogItemDetailSchema, { signal }),
  };
}
