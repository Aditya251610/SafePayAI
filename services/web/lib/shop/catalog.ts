import type { CatalogItem } from "@/lib/api/schemas/catalog";
import { merchantLabel } from "@/lib/format/label";

export const PAGE_SIZE = 24;
export const MAX_QTY = 5;
export const PLACEHOLDER_IMAGE = "/products/placeholder.svg";

export type SortKey = "name" | "price-asc" | "price-desc";

export interface ShopFilters {
  query: string;
  category: string | null;
  merchant: string | null;
  sort: SortKey;
}

export const DEFAULT_FILTERS: ShopFilters = {
  query: "",
  category: null,
  merchant: null,
  sort: "name",
};

/** Static product picture. The file name is the sku, encoded so an odd sku cannot escape the folder. */
export function productImage(sku: string): string {
  return `/products/${encodeURIComponent(sku)}.svg`;
}

/** "kitchen_tools" becomes "Kitchen Tools". */
export function categoryLabel(id: string): string {
  return id
    .split(/[_\-\s]/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/** Item text is untrusted. Shown as plain text, cut to a length that fits the surface. */
export function clip(text: string, max: number): string {
  const t = text.replace(/\s+/g, " ").trim();
  return t.length > max ? `${t.slice(0, max - 1).trimEnd()}…` : t;
}

function matches(item: CatalogItem, f: ShopFilters, skip?: "category" | "merchant"): boolean {
  const q = f.query.trim().toLowerCase();
  if (q && !item.title.toLowerCase().includes(q)) return false;
  if (skip !== "category" && f.category && item.category_id !== f.category) return false;
  if (skip !== "merchant" && f.merchant && item.merchant_id !== f.merchant) return false;
  return true;
}

function compare(a: CatalogItem, b: CatalogItem, sort: SortKey): number {
  if (sort === "name") return a.title.localeCompare(b.title) || a.sku.localeCompare(b.sku);
  // Ordering two prices is a comparison, not arithmetic on money.
  const lt = a.unit_price_minor < b.unit_price_minor;
  const gt = a.unit_price_minor > b.unit_price_minor;
  const order = lt ? -1 : gt ? 1 : 0;
  return (sort === "price-asc" ? order : -order) || a.title.localeCompare(b.title);
}

export function filterAndSort(items: readonly CatalogItem[], f: ShopFilters): CatalogItem[] {
  return items.filter((i) => i.active && matches(i, f)).sort((a, b) => compare(a, b, f.sort));
}

export interface Facet {
  id: string;
  label: string;
  count: number;
}

function facet(items: readonly CatalogItem[], f: ShopFilters, by: "category" | "merchant") {
  const counts = new Map<string, number>();
  for (const i of items) {
    if (!i.active || !matches(i, f, by)) continue;
    const id = by === "category" ? i.category_id : i.merchant_id;
    counts.set(id, (counts.get(id) ?? 0) + 1);
  }
  return Array.from(counts, ([id, count]) => ({
    id,
    count,
    label: by === "category" ? categoryLabel(id) : merchantLabel(id),
  })).sort((a, b) => a.label.localeCompare(b.label));
}

/** Chip counts, each ignoring its own filter so the other chips show what is still reachable. */
export const categoryFacets = (items: readonly CatalogItem[], f: ShopFilters): Facet[] =>
  facet(items, f, "category");
export const merchantFacets = (items: readonly CatalogItem[], f: ShopFilters): Facet[] =>
  facet(items, f, "merchant");
