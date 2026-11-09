import { z } from "zod";

import { loadEntry, saveEntry } from "@/lib/storage/session-cache";
import { merchantLabel } from "@/lib/format/label";

import { MAX_QTY } from "./catalog";

/**
 * The shopping basket: skus and quantities only, never prices. The server prices the cart,
 * so nothing in the browser adds money up. Kept for the tab, like carts and proposals.
 */
export const basketLineSchema = z.object({
  sku: z.string().min(1),
  title: z.string(),
  merchantId: z.string(),
  qty: z.number().int().min(1).max(MAX_QTY),
});
export type BasketLine = z.infer<typeof basketLineSchema>;

const basketSchema = z.object({ lines: z.array(basketLineSchema).max(60) });

const KEY = "basket";

export const loadBasket = (): BasketLine[] => loadEntry(KEY, basketSchema)?.lines ?? [];
export const saveBasket = (lines: BasketLine[]) => saveEntry(KEY, { lines });

export const clampQty = (qty: number): number => Math.min(MAX_QTY, Math.max(1, Math.trunc(qty)));

/** Adds a line, merging with an existing one for the same sku (capped at the per-line maximum). */
export function addLine(lines: readonly BasketLine[], add: BasketLine): BasketLine[] {
  const existing = lines.find((l) => l.sku === add.sku);
  if (!existing) return [...lines, { ...add, qty: clampQty(add.qty) }];
  return lines.map((l) => (l.sku === add.sku ? { ...l, qty: clampQty(l.qty + add.qty) } : l));
}

export function setQty(lines: readonly BasketLine[], sku: string, qty: number): BasketLine[] {
  return lines.map((l) => (l.sku === sku ? { ...l, qty: clampQty(qty) } : l));
}

export const removeLine = (lines: readonly BasketLine[], sku: string): BasketLine[] =>
  lines.filter((l) => l.sku !== sku);

export interface BasketGroup {
  merchantId: string;
  label: string;
  lines: BasketLine[];
}

/** Lines grouped by shop, in the order each shop was first added. */
export function groupByMerchant(lines: readonly BasketLine[]): BasketGroup[] {
  const groups = new Map<string, BasketGroup>();
  for (const l of lines) {
    const g = groups.get(l.merchantId) ?? {
      merchantId: l.merchantId,
      label: merchantLabel(l.merchantId),
      lines: [],
    };
    g.lines.push(l);
    groups.set(l.merchantId, g);
  }
  return Array.from(groups.values());
}

/** Units in the basket (a count of items, not an amount of money). */
export const unitCount = (lines: readonly BasketLine[]): number =>
  lines.reduce((n, l) => n + l.qty, 0);
