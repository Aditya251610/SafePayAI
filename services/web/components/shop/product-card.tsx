"use client";

import * as React from "react";

import { ProductImage } from "@/components/shop/product-image";
import { QtyStepper } from "@/components/shop/qty-stepper";
import { Button } from "@/components/ui/button";
import { Slab } from "@/components/ui/slab";
import { Tag } from "@/components/ui/tag";
import type { CatalogItem } from "@/lib/api/schemas/catalog";
import { merchantLabel } from "@/lib/format/label";
import { formatMoney } from "@/lib/format/money";
import { categoryLabel, clip } from "@/lib/shop/catalog";

export function ProductCard({
  item,
  maxQtyHint,
  onAdd,
  onOpen,
}: {
  item: CatalogItem;
  maxQtyHint?: number | null;
  onAdd: (item: CatalogItem, qty: number) => void;
  onOpen: (item: CatalogItem) => void;
}) {
  const [qty, setQty] = React.useState(1);
  return (
    <li className="flex">
      <Slab className="flex w-full flex-col gap-3 p-0">
        <button
          type="button"
          onClick={() => onOpen(item)}
          aria-label={`Quick view: ${item.title}`}
          className="block border-b-2 border-line"
        >
          <ProductImage sku={item.sku} />
        </button>
        <div className="flex flex-1 flex-col gap-3 px-4 pb-4">
          <div className="flex flex-wrap gap-2">
            <Tag tone="seal">{merchantLabel(item.merchant_id)}</Tag>
            <Tag>{categoryLabel(item.category_id)}</Tag>
          </div>
          <h3 className="text-base font-semibold leading-snug">{item.title}</h3>
          <p className="text-sm text-mute">{clip(item.description, 90)}</p>
          <p className="tabular mt-auto text-xl font-semibold">
            {formatMoney(item.unit_price_minor, item.currency)}
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <QtyStepper value={qty} onChange={setQty} label={item.title} />
            <Button className="flex-1" onClick={() => onAdd(item, qty)}>
              Add to basket
              <span className="sr-only"> {item.title}</span>
            </Button>
          </div>
          <p className="text-xs text-dim">
            1 to 5 per line
            {maxQtyHint ? ` · your mandate allows up to ${maxQtyHint} per line` : ""}
          </p>
        </div>
      </Slab>
    </li>
  );
}
