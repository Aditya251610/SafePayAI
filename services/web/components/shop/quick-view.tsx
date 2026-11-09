"use client";

import * as React from "react";

import { ProductImage } from "@/components/shop/product-image";
import { QtyStepper } from "@/components/shop/qty-stepper";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { Tag } from "@/components/ui/tag";
import type { CatalogItem } from "@/lib/api/schemas/catalog";
import { merchantLabel } from "@/lib/format/label";
import { formatMoney } from "@/lib/format/money";
import { categoryLabel, clip } from "@/lib/shop/catalog";

function Body({ item, onAdd }: { item: CatalogItem; onAdd: (i: CatalogItem, q: number) => void }) {
  const [qty, setQty] = React.useState(1);
  return (
    <div className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto">
      <ProductImage sku={item.sku} alt={item.title} priority />
      <div className="flex flex-wrap gap-2">
        <Tag tone="seal">{merchantLabel(item.merchant_id)}</Tag>
        <Tag>{categoryLabel(item.category_id)}</Tag>
        <Tag tone="dashed">Seeded catalog</Tag>
      </div>
      {/* Item text is untrusted: rendered as plain text only. */}
      <p className="whitespace-pre-line text-sm text-mute">{clip(item.description, 600)}</p>
      <p className="tabular text-2xl font-semibold">
        {formatMoney(item.unit_price_minor, item.currency)}
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <QtyStepper value={qty} onChange={setQty} label={item.title} />
        <Button className="flex-1" onClick={() => onAdd(item, qty)}>
          Add to basket
        </Button>
        <DialogClose asChild>
          <Button variant="secondary">Close</Button>
        </DialogClose>
      </div>
    </div>
  );
}

/** One dialog for the whole grid. Radix traps focus, closes on Escape and returns focus. */
export function QuickView({
  item,
  onClose,
  onAdd,
}: {
  item: CatalogItem | null;
  onClose: () => void;
  onAdd: (item: CatalogItem, qty: number) => void;
}) {
  return (
    <Dialog open={item !== null} onOpenChange={(o) => !o && onClose()}>
      {item && (
        <DialogContent title={item.title} className="max-w-xl">
          <Body
            item={item}
            onAdd={(i, q) => {
              onAdd(i, q);
              onClose();
            }}
          />
        </DialogContent>
      )}
    </Dialog>
  );
}
