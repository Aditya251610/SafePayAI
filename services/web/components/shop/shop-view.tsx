"use client";

import * as React from "react";

import { ApiErrorNotice } from "@/components/shared/api-error";
import { WakingUp } from "@/components/shared/waking-up";
import { BasketPanel } from "@/components/shop/basket-panel";
import { ProductCard } from "@/components/shop/product-card";
import { QuickView } from "@/components/shop/quick-view";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/errors";
import type { CatalogItem } from "@/lib/api/schemas/catalog";
import { useBuyerHome, useShopCatalog } from "@/lib/hooks/queries";
import {
  addLine,
  loadBasket,
  removeLine,
  saveBasket,
  setQty,
  unitCount,
  type BasketLine,
} from "@/lib/shop/basket";
import {
  DEFAULT_FILTERS,
  PAGE_SIZE,
  categoryFacets,
  filterAndSort,
  merchantFacets,
  type Facet,
  type ShopFilters,
  type SortKey,
} from "@/lib/shop/catalog";
import { cn } from "@/lib/utils";

function Chips({
  label,
  facets,
  value,
  onPick,
}: {
  label: string;
  facets: Facet[];
  value: string | null;
  onPick: (id: string | null) => void;
}) {
  const chip = (on: boolean) =>
    cn(
      "inline-flex min-h-12 items-center border-2 px-3 text-xs font-bold uppercase tracking-[0.08em] md:min-h-9",
      on ? "border-fg bg-fg text-bg" : "border-line-strong text-mute hover:border-fg",
    );
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2">
      <button
        type="button"
        aria-pressed={value === null}
        className={chip(value === null)}
        onClick={() => onPick(null)}
      >
        All
      </button>
      {facets.map((f) => (
        <button
          key={f.id}
          type="button"
          aria-pressed={value === f.id}
          className={chip(value === f.id)}
          onClick={() => onPick(value === f.id ? null : f.id)}
        >
          {f.label} ({f.count})
        </button>
      ))}
    </div>
  );
}

export function ShopView() {
  const catalog = useShopCatalog();
  const home = useBuyerHome();
  const [filters, setFilters] = React.useState<ShopFilters>(DEFAULT_FILTERS);
  const [shown, setShown] = React.useState(PAGE_SIZE);
  const [lines, setLines] = React.useState<BasketLine[]>([]);
  const [hydrated, setHydrated] = React.useState(false);
  const [quick, setQuick] = React.useState<CatalogItem | null>(null);
  const [drawer, setDrawer] = React.useState(false);
  const [notice, setNotice] = React.useState("");

  React.useEffect(() => {
    setLines(loadBasket());
    setHydrated(true);
  }, []);
  React.useEffect(() => {
    if (hydrated) saveBasket(lines);
  }, [lines, hydrated]);

  const items = React.useMemo(() => catalog.data ?? [], [catalog.data]);
  const results = React.useMemo(() => filterAndSort(items, filters), [items, filters]);
  const categories = React.useMemo(() => categoryFacets(items, filters), [items, filters]);
  const merchants = React.useMemo(() => merchantFacets(items, filters), [items, filters]);
  const maxQtyHint =
    (home.data?.mandates ?? []).find((m) => m.status === "active")?.max_qty_per_line ?? null;

  function update(patch: Partial<ShopFilters>) {
    setFilters((f) => ({ ...f, ...patch }));
    setShown(PAGE_SIZE);
  }

  const add = React.useCallback((item: CatalogItem, qty: number) => {
    setLines((l) =>
      addLine(l, { sku: item.sku, title: item.title, merchantId: item.merchant_id, qty }),
    );
    setNotice(`Added ${item.title} to the basket.`);
  }, []);

  const basket = (
    <BasketPanel
      lines={lines}
      onQty={(sku, qty) => setLines((l) => setQty(l, sku, qty))}
      onRemove={(sku) => setLines((l) => removeLine(l, sku))}
    />
  );
  const count = unitCount(lines);

  if (catalog.isPending) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-72 w-full" />
        ))}
      </div>
    );
  }
  if (catalog.isError) {
    return catalog.error instanceof ApiError && catalog.error.code === "UPSTREAM_WAKING" ? (
      <WakingUp />
    ) : (
      <ApiErrorNotice error={catalog.error} onRetry={() => void catalog.refetch()} />
    );
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="flex min-w-0 flex-col gap-6">
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex min-w-[220px] flex-1 flex-col gap-1 text-sm">
            <span className="font-semibold">Search by name</span>
            <input
              type="search"
              value={filters.query}
              onChange={(e) => update({ query: e.target.value })}
              placeholder="Try “kettle” or “earbuds”"
              className="h-12 border-2 border-line-strong bg-panel px-3"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-semibold">Sort</span>
            <select
              value={filters.sort}
              onChange={(e) => update({ sort: e.target.value as SortKey })}
              className="h-12 border-2 border-line-strong bg-panel px-3"
            >
              <option value="name">Name</option>
              <option value="price-asc">Price, low to high</option>
              <option value="price-desc">Price, high to low</option>
            </select>
          </label>
        </div>

        <Chips
          label="Shop"
          facets={merchants}
          value={filters.merchant}
          onPick={(id) => update({ merchant: id })}
        />
        <Chips
          label="Category"
          facets={categories}
          value={filters.category}
          onPick={(id) => update({ category: id })}
        />

        <p className="text-sm text-mute" role="status">
          {results.length} {results.length === 1 ? "product" : "products"}
        </p>
        <p className="sr-only" role="status">
          {notice}
        </p>

        {results.length === 0 ? (
          <p className="border-2 border-dashed border-line-strong p-6 text-mute">
            Nothing matches. Clear the search or pick another filter.
          </p>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {results.slice(0, shown).map((item) => (
              <ProductCard
                key={item.sku}
                item={item}
                maxQtyHint={maxQtyHint}
                onAdd={add}
                onOpen={setQuick}
              />
            ))}
          </ul>
        )}

        {results.length > shown && (
          <Button
            variant="secondary"
            size="lg"
            className="self-center"
            onClick={() => setShown((n) => n + PAGE_SIZE)}
          >
            Load more ({results.length - shown} left)
          </Button>
        )}
        <p className="text-xs text-dim">
          Seeded catalog, not a live store. Prices come from the catalog, and the server checks the
          cart.
        </p>
      </div>

      <aside className="hidden lg:block">
        <div className="sticky top-6">{basket}</div>
      </aside>

      <div className="fixed inset-x-0 bottom-[calc(3rem+env(safe-area-inset-bottom,0px))] z-20 border-t-2 border-line bg-panel p-2 md:bottom-0 md:left-[72px] lg:hidden">
        <Button className="w-full" onClick={() => setDrawer(true)}>
          Basket · {count} {count === 1 ? "item" : "items"}
        </Button>
      </div>
      <Dialog open={drawer} onOpenChange={setDrawer}>
        <DialogContent title="Your basket" className="max-w-md">
          {basket}
        </DialogContent>
      </Dialog>

      <QuickView item={quick} onClose={() => setQuick(null)} onAdd={add} />
    </div>
  );
}
