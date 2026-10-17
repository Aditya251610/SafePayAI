import { z } from "zod";

export const catalogItemSchema = z.object({
  sku: z.string(),
  merchant_id: z.string(),
  category_id: z.string(),
  title: z.string(),
  description: z.string(),
  unit_price_minor: z.number().int(),
  currency: z.string(),
  active: z.boolean(),
  text_trust: z.string().nullish(),
  label: z.string().nullish(),
});
export type CatalogItem = z.infer<typeof catalogItemSchema>;

export const catalogListSchema = z.object({
  catalog_version: z.number().int(),
  items: z.array(catalogItemSchema),
  limit: z.number().int(),
  offset: z.number().int(),
  has_more: z.boolean(),
});
export type CatalogList = z.infer<typeof catalogListSchema>;

export const catalogItemDetailSchema = catalogItemSchema.extend({
  catalog_version: z.number().int(),
});
export type CatalogItemDetail = z.infer<typeof catalogItemDetailSchema>;
