"use client";

import * as React from "react";
import Link from "next/link";

import { ApiErrorNotice } from "@/components/shared/api-error";
import { WakingUp } from "@/components/shared/waking-up";
import { Button } from "@/components/ui/button";
import { OrderDetail } from "@/components/orders/order-detail";
import { Skeleton } from "@/components/ui/skeleton";
import { Slab } from "@/components/ui/slab";
import { Table, TableWrap, Td, Th } from "@/components/ui/data-table";
import { Tag } from "@/components/ui/tag";
import { ApiError } from "@/lib/api/errors";
import type { Order } from "@/lib/api/schemas/checkout";
import { formatDate } from "@/lib/format/date";
import { orderStatusLabel, shortId } from "@/lib/format/label";
import { formatMoney } from "@/lib/format/money";
import { useOrders } from "@/lib/hooks/queries";
import { cn } from "@/lib/utils";

export function orderTone(status: string) {
  if (status === "CAPTURED") return "ret" as const;
  if (status.startsWith("CANCELLED") || status === "EXPIRED") return "neutral" as const;
  if (status.endsWith("FAILED")) return "flare" as const;
  return "seal" as const;
}

function items(o: Order): string {
  return (o.item_titles ?? []).join(", ") || "Order";
}

export function OrdersList() {
  const orders = useOrders(20);
  const [picked, setPicked] = React.useState<string | null>(null);

  if (orders.isPending) {
    return (
      <div className="flex flex-col gap-3" aria-busy="true">
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-14 w-full" />
      </div>
    );
  }
  if (orders.isError) {
    return orders.error instanceof ApiError && orders.error.code === "UPSTREAM_WAKING" ? (
      <WakingUp />
    ) : (
      <ApiErrorNotice error={orders.error} onRetry={() => void orders.refetch()} />
    );
  }

  const list = orders.data.items;
  if (list.length === 0) {
    return (
      <Slab className="flex max-w-xl flex-col items-start gap-3">
        <p className="font-semibold">No orders yet.</p>
        <p className="text-sm text-mute">
          Nothing was spent. Ask the agent for a cart to place one.
        </p>
        <Button asChild>
          <Link href="/intent">State what you need</Link>
        </Button>
      </Slab>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-dim">
        {list.length} {list.length === 1 ? "order" : "orders"} · newest first · up to 20
      </p>

      <TableWrap className="hidden lg:block">
        <Table>
          <thead>
            <tr>
              <Th>Order</Th>
              <Th>Items</Th>
              <Th>Date</Th>
              <Th className="text-right">Total</Th>
              <Th>Status</Th>
            </tr>
          </thead>
          <tbody>
            {list.map((o) => (
              <tr key={o.order_id}>
                <Td>
                  <Link
                    href={`/orders/${o.order_id}`}
                    className="font-mono text-seal underline-offset-4 hover:underline"
                  >
                    ORD-{shortId(o.order_id, 6)}
                  </Link>
                </Td>
                <Td>{items(o)}</Td>
                <Td>{formatDate(o.created_at)}</Td>
                <Td className="text-right">{formatMoney(o.total_minor, o.currency)}</Td>
                <Td>
                  <Tag tone={orderTone(o.status)}>{orderStatusLabel(o.status)}</Tag>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </TableWrap>

      <div className="hidden gap-6 md:grid md:grid-cols-[minmax(0,20rem)_minmax(0,1fr)] lg:hidden">
        <ul className="flex flex-col gap-2" aria-label="Orders">
          {list.map((o) => (
            <li key={o.order_id}>
              <button
                type="button"
                aria-pressed={(picked ?? list[0]?.order_id) === o.order_id}
                onClick={() => setPicked(o.order_id)}
                className={cn(
                  "flex min-h-12 w-full flex-col gap-1 border-2 p-3 text-left",
                  (picked ?? list[0]?.order_id) === o.order_id
                    ? "border-fg bg-panel"
                    : "border-line bg-panel hover:border-line-strong",
                )}
              >
                <span className="flex items-baseline justify-between gap-3">
                  <span className="font-mono text-sm text-seal">ORD-{shortId(o.order_id, 6)}</span>
                  <span className="tabular font-semibold">
                    {formatMoney(o.total_minor, o.currency)}
                  </span>
                </span>
                <span className="text-xs text-mute">
                  {items(o)} · {formatDate(o.created_at)}
                </span>
                <Tag tone={orderTone(o.status)} className="self-start">
                  {orderStatusLabel(o.status)}
                </Tag>
              </button>
            </li>
          ))}
        </ul>
        <div className="min-w-0 border-2 border-line p-5" data-testid="order-pane">
          <OrderDetail
            key={picked ?? list[0]?.order_id}
            orderId={picked ?? list[0]?.order_id}
            embedded
          />
          <Link
            href={`/orders/${picked ?? list[0]?.order_id}`}
            className="mt-4 inline-block text-sm font-semibold text-seal underline-offset-4 hover:underline"
          >
            Open as a page →
          </Link>
        </div>
      </div>

      <ul className="flex flex-col gap-3 md:hidden">
        {list.map((o) => (
          <li key={o.order_id}>
            <Link href={`/orders/${o.order_id}`} className="block">
              <Slab className="flex min-h-12 flex-col gap-2">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-mono text-sm text-seal">ORD-{shortId(o.order_id, 6)}</span>
                  <span className="tabular text-lg font-semibold">
                    {formatMoney(o.total_minor, o.currency)}
                  </span>
                </div>
                <p className="text-sm text-mute">
                  {items(o)} · {formatDate(o.created_at)}
                </p>
                <Tag tone={orderTone(o.status)} className="self-start">
                  {orderStatusLabel(o.status)}
                </Tag>
              </Slab>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
