"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { AgentWorking, useElapsed } from "@/components/agent/agent-working";
import { ProductImage } from "@/components/shop/product-image";
import { QtyStepper } from "@/components/shop/qty-stepper";
import { ApiErrorNotice } from "@/components/shared/api-error";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { Slab } from "@/components/ui/slab";
import { Tag } from "@/components/ui/tag";
import { api } from "@/lib/api";
import { newIdempotencyKey } from "@/lib/api/ids";
import { formatDate } from "@/lib/format/date";
import { useBuyerHome } from "@/lib/hooks/queries";
import { groupByMerchant, unitCount, type BasketLine } from "@/lib/shop/basket";
import { saveCart } from "@/lib/storage/entries";

/**
 * The basket. It lists skus and quantities only. The server prices the cart and checks it
 * against the mandate; this panel never adds money up.
 */
export function BasketPanel({
  lines,
  onQty,
  onRemove,
}: {
  lines: readonly BasketLine[];
  onQty: (sku: string, qty: number) => void;
  onRemove: (sku: string) => void;
}) {
  const router = useRouter();
  const home = useBuyerHome();
  const active = (home.data?.mandates ?? []).filter((m) => m.status === "active");
  const [mandateId, setMandateId] = React.useState("");
  const selected = active.find((m) => m.mandate_id === mandateId) ?? active[0];
  const [pending, setPending] = React.useState(false);
  const [failure, setFailure] = React.useState<unknown>(null);
  const key = React.useRef<{ key: string; sig: string } | null>(null);
  const seconds = useElapsed(pending);

  const groups = groupByMerchant(lines);
  const count = unitCount(lines);

  async function check() {
    if (!selected || lines.length === 0) return;
    setFailure(null);
    setPending(true);
    // The same basket and mandate reuse one key, so a retry is answered once by the server.
    const sig = JSON.stringify([selected.mandate_id, lines.map((l) => [l.sku, l.qty])]);
    if (key.current?.sig !== sig) key.current = { key: newIdempotencyKey(), sig };
    try {
      const cart = await api.checkout.createCart(
        {
          mandate_id: selected.mandate_id,
          lines: lines.map((l) => ({ sku: l.sku, qty: l.qty })),
        },
        { idempotencyKey: key.current.key },
      );
      saveCart({ cart, mandateId: selected.mandate_id });
      router.push(`/cart/${cart.cart_id}`);
    } catch (e) {
      setFailure(e);
      setPending(false);
    }
  }

  return (
    <Slab raised notched className="flex flex-col gap-4" aria-label="Basket">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-display text-2xl font-extrabold">Basket</h2>
        <Tag tone="seal">
          {count} {count === 1 ? "item" : "items"}
        </Tag>
      </div>

      {lines.length === 0 ? (
        <p className="text-sm text-mute">Nothing here yet. Add items from the shop.</p>
      ) : (
        <div className="flex max-h-[45vh] flex-col gap-4 overflow-y-auto">
          {groups.map((g) => (
            <section key={g.merchantId} aria-label={`From ${g.label}`}>
              <p className="border-b border-line pb-1 text-xs font-bold uppercase tracking-[0.14em] text-dim">
                {g.label}
              </p>
              <ul>
                {g.lines.map((l) => (
                  <li key={l.sku} className="flex flex-col gap-2 border-b border-line py-3">
                    <div className="flex items-center gap-3">
                      <ProductImage sku={l.sku} className="w-16 shrink-0 border border-line" />
                      <p className="min-w-0 flex-1 text-sm font-semibold">{l.title}</p>
                    </div>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <QtyStepper value={l.qty} onChange={(n) => onQty(l.sku, n)} label={l.title} />
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Remove ${l.title}`}
                        onClick={() => onRemove(l.sku)}
                      >
                        Remove
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      <p className="text-xs text-dim">
        Totals and the cap check are done by the server, not this page.
      </p>

      {!home.isPending && active.length === 0 && (
        <Notice tone="info" title="Sign a mandate first">
          <p>The cap check needs an active mandate.</p>
          <Button asChild className="mt-3" size="sm">
            <Link href="/mandate/new">Sign a mandate</Link>
          </Button>
        </Notice>
      )}

      {active.length > 1 && (
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-semibold">Check against</span>
          <select
            className="h-12 border-2 border-line-strong bg-panel px-3"
            value={selected?.mandate_id ?? ""}
            onChange={(e) => setMandateId(e.target.value)}
          >
            {active.map((m) => (
              <option key={m.mandate_id} value={m.mandate_id}>
                {m.intent_text ? m.intent_text.slice(0, 40) : "Mandate"} · until{" "}
                {formatDate(m.expires_at)}
              </option>
            ))}
          </select>
        </label>
      )}

      {pending ? (
        <AgentWorking
          seconds={seconds}
          label="Checking the basket against your mandate. Rules decide each check."
          onRetry={() => void check()}
        />
      ) : (
        <Button size="lg" disabled={!selected || lines.length === 0} onClick={() => void check()}>
          Check against my mandate
        </Button>
      )}
      {failure !== null && <ApiErrorNotice error={failure} onRetry={() => void check()} />}
    </Slab>
  );
}
