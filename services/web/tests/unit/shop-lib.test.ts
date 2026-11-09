import { describe, expect, it } from "vitest";
import * as f from "../mocks/fixtures";
import {
  DEFAULT_FILTERS,
  categoryFacets,
  clip,
  filterAndSort,
  merchantFacets,
  productImage,
} from "@/lib/shop/catalog";
import { addLine, groupByMerchant, removeLine, setQty, unitCount } from "@/lib/shop/basket";
import { catalogListSchema } from "@/lib/api/schemas/catalog";

const items = catalogListSchema.parse(f.shopCatalog()).items;

describe("shop catalog helpers", () => {
  it("builds 180 deterministic items, 60 per shop", () => {
    expect(items).toHaveLength(180);
    expect(merchantFacets(items, DEFAULT_FILTERS).map((m) => m.count)).toEqual([60, 60, 60]);
    expect(f.shopItems()).toEqual(f.shopItems());
  });

  it("filters by title, category and shop, with counts that ignore their own filter", () => {
    const f1 = { ...DEFAULT_FILTERS, merchant: "mrc_hearth" };
    expect(filterAndSort(items, f1)).toHaveLength(60);
    expect(categoryFacets(items, f1).map((c) => c.id)).toEqual([
      "gifts",
      "home",
      "kitchen",
      "pantry",
    ]);
    expect(merchantFacets(items, f1)).toHaveLength(3);
    const f2 = { ...f1, query: "KITCHEN ITEM 01" };
    expect(filterAndSort(items, f2).map((i) => i.sku)).toEqual(["HEA-01"]);
  });

  it("sorts by name and by price in both directions", () => {
    const asc = filterAndSort(items, { ...DEFAULT_FILTERS, sort: "price-asc" });
    const desc = filterAndSort(items, { ...DEFAULT_FILTERS, sort: "price-desc" });
    expect(asc[0]?.unit_price_minor).toBeLessThanOrEqual(asc[1]?.unit_price_minor ?? 0);
    expect(desc[0]?.unit_price_minor).toBeGreaterThanOrEqual(desc[1]?.unit_price_minor ?? 0);
    const byName = filterAndSort(items, DEFAULT_FILTERS).map((i) => i.title);
    expect(byName).toEqual([...byName].sort((a, b) => a.localeCompare(b)));
  });

  it("hides inactive items, clips text and encodes image paths", () => {
    const hidden = [{ ...items[0]!, active: false }];
    expect(filterAndSort(hidden, DEFAULT_FILTERS)).toEqual([]);
    expect(clip("a  b\n c", 100)).toBe("a b c");
    expect(clip("x".repeat(50), 10)).toHaveLength(10);
    expect(productImage("../a b")).toBe("/products/..%2Fa%20b.svg");
  });
});

describe("basket helpers", () => {
  const line = (sku: string, merchantId: string, qty = 1) => ({
    sku,
    title: sku,
    merchantId,
    qty,
  });

  it("merges, clamps to 1..5, removes and counts", () => {
    let b = addLine([], line("A", "mrc_x", 3));
    b = addLine(b, line("A", "mrc_x", 4));
    expect(b[0]?.qty).toBe(5);
    b = setQty(b, "A", 0);
    expect(b[0]?.qty).toBe(1);
    b = addLine(b, line("B", "mrc_y", 2));
    expect(unitCount(b)).toBe(3);
    expect(removeLine(b, "A").map((l) => l.sku)).toEqual(["B"]);
  });

  it("groups lines by shop", () => {
    const g = groupByMerchant([line("A", "mrc_x"), line("B", "mrc_y"), line("C", "mrc_x")]);
    expect(g.map((x) => [x.label, x.lines.length])).toEqual([
      ["X", 2],
      ["Y", 1],
    ]);
  });
});
