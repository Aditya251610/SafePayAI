"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { ApiErrorNotice } from "@/components/shared/api-error";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { Slab } from "@/components/ui/slab";
import { Table, TableWrap, Td, Th } from "@/components/ui/data-table";
import { Tag } from "@/components/ui/tag";
import { api } from "@/lib/api";
import { isUuid, newIdempotencyKey } from "@/lib/api/ids";
import type { CreateShipmentResponse } from "@/lib/api/schemas/tracking";
import { OUTCOME_PROFILES } from "@/lib/api/schemas/tracking";
import { formatDate } from "@/lib/format/date";
import { caseKindLabel, caseStateLabel, orderStatusLabel, shortId } from "@/lib/format/label";
import { formatMoney } from "@/lib/format/money";
import { useMerchantQueue } from "@/lib/hooks/queries";
import { SIMULATED_CARRIER_LABEL } from "@/lib/honesty/copy";
import { cn } from "@/lib/utils";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "HUMAN_REVIEW", label: "With a reviewer" },
  { id: "OFFERED", label: "Offered" },
  { id: "DECLINED", label: "Declined" },
] as const;

function Queue() {
  const q = useMerchantQueue();
  const [filter, setFilter] = React.useState<(typeof FILTERS)[number]["id"]>("all");

  if (q.isPending) return <Skeleton className="h-40 w-full" />;
  if (q.isError) return <ApiErrorNotice error={q.error} onRetry={() => void q.refetch()} />;

  // The service ignores its state filter today, so the list is narrowed here.
  const all = q.data.cases;
  const cases = filter === "all" ? all : all.filter((c) => c.state === filter);
  const pending = q.data.tracking_pending;

  return (
    <section aria-labelledby="queue-h" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3 border-t-4 border-fg pt-3">
        <h2 id="queue-h" className="text-xl font-semibold">
          Case queue
        </h2>
        <Tag tone={pending === null || pending === undefined ? "dashed" : "seal"}>
          {pending === null || pending === undefined
            ? "Tracking count unavailable"
            : `${pending} shipments in motion`}
        </Tag>
      </div>
      {pending === null || pending === undefined ? (
        <p className="text-xs text-dim">tracking_pending is null. The queue still loads.</p>
      ) : null}
      <div role="group" aria-label="Filter cases" className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            aria-pressed={filter === f.id}
            onClick={() => setFilter(f.id)}
            className={cn(
              "h-12 border-2 px-3 text-xs font-bold uppercase tracking-[0.08em] md:h-9",
              filter === f.id ? "border-fg text-fg" : "border-line-strong text-dim hover:text-fg",
            )}
          >
            {f.label}
          </button>
        ))}
      </div>
      {cases.length === 0 ? (
        <Slab>
          <p className="text-sm text-mute">No cases here.</p>
        </Slab>
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Case</Th>
                <Th>Order</Th>
                <Th>Kind</Th>
                <Th>State</Th>
                <Th>Opened</Th>
                <Th>
                  <span className="sr-only">Open</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.case_id}>
                  <Td className="font-mono">CSE-{shortId(c.case_id, 6)}</Td>
                  <Td className="font-mono">ORD-{shortId(c.order_id, 6)}</Td>
                  <Td>{caseKindLabel(c.kind)}</Td>
                  <Td>
                    <Tag tone={c.state === "HUMAN_REVIEW" ? "seal" : "neutral"}>
                      {caseStateLabel(c.state)}
                    </Tag>
                  </Td>
                  <Td>{formatDate(c.opened_at)}</Td>
                  <Td>
                    <Link
                      href={`/merchant/cases/${c.case_id}`}
                      className="font-semibold text-seal underline-offset-4 hover:underline"
                    >
                      Open
                    </Link>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </TableWrap>
      )}
    </section>
  );
}

function OrdersLookup({ onPick }: { onPick: (orderId: string) => void }) {
  const [input, setInput] = React.useState("");
  const [mandateId, setMandateId] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const q = useQuery({
    queryKey: ["merchant-orders", mandateId] as const,
    queryFn: ({ signal }) =>
      api.checkout.orders({ mandateId: mandateId ?? undefined, limit: 50 }, signal),
    enabled: mandateId !== null,
    retry: false,
  });

  return (
    <section aria-labelledby="orders-h" className="flex flex-col gap-3">
      <h2 id="orders-h" className="border-t-4 border-fg pt-3 text-xl font-semibold">
        Orders for a mandate
      </h2>
      <p className="text-sm text-mute">
        Merchants and operators pick a mandate first. You only ever see your own shop&apos;s orders.
      </p>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (!isUuid(input.trim())) {
            setError("Paste a mandate id.");
            return;
          }
          setError(null);
          setMandateId(input.trim());
        }}
      >
        <div className="w-full sm:w-96">
          <Field
            id="mandate-id"
            label="Mandate id"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            error={error ?? undefined}
          />
        </div>
        <Button type="submit" variant="secondary">
          Show orders
        </Button>
      </form>
      {q.isFetching ? (
        <Skeleton className="h-16 w-full" />
      ) : q.isError ? (
        <ApiErrorNotice error={q.error} onRetry={() => void q.refetch()} />
      ) : q.data ? (
        q.data.items.length === 0 ? (
          <Slab>
            <p className="text-sm text-mute">No orders for that mandate.</p>
          </Slab>
        ) : (
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>Order</Th>
                  <Th>Items</Th>
                  <Th className="text-right">Total</Th>
                  <Th>Status</Th>
                  <Th>
                    <span className="sr-only">Use</span>
                  </Th>
                </tr>
              </thead>
              <tbody>
                {q.data.items.map((o) => (
                  <tr key={o.order_id}>
                    <Td className="font-mono">ORD-{shortId(o.order_id, 6)}</Td>
                    <Td>{(o.item_titles ?? []).join(", ") || "Order"}</Td>
                    <Td className="text-right">{formatMoney(o.total_minor, o.currency)}</Td>
                    <Td>{orderStatusLabel(o.status)}</Td>
                    <Td>
                      <Button size="sm" variant="secondary" onClick={() => onPick(o.order_id)}>
                        Ship this
                      </Button>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrap>
        )
      ) : null}
    </section>
  );
}

function ShipForm({ orderId, setOrderId }: { orderId: string; setOrderId: (v: string) => void }) {
  const [tracking, setTracking] = React.useState("");
  const [carrier, setCarrier] = React.useState("");
  const [profile, setProfile] = React.useState<(typeof OUTCOME_PROFILES)[number]>("ON_TIME");
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [busy, setBusy] = React.useState(false);
  const [failure, setFailure] = React.useState<unknown>(null);
  const [done, setDone] = React.useState<CreateShipmentResponse | null>(null);
  const key = React.useRef<string | null>(null);

  async function submit() {
    const errs: Record<string, string> = {};
    if (!isUuid(orderId.trim())) errs.order = "Paste the order id.";
    if (!tracking.trim()) errs.tracking = "Enter a tracking number.";
    if (!carrier.trim()) errs.carrier = "Enter a carrier name.";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    setFailure(null);
    key.current ??= newIdempotencyKey();
    try {
      setDone(
        await api.tracking.createShipment(
          {
            order_id: orderId.trim(),
            tracking_number: tracking.trim(),
            carrier_name: carrier.trim(),
            outcome_profile: profile,
          },
          { idempotencyKey: key.current },
        ),
      );
    } catch (e) {
      setFailure(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="ship-h" className="flex flex-col gap-3">
      <h2 id="ship-h" className="border-t-4 border-fg pt-3 text-xl font-semibold">
        Mark an order shipped
      </h2>
      <form
        className="grid gap-4 sm:grid-cols-2"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div className="sm:col-span-2">
          <Field
            id="ship-order"
            label="Order id"
            value={orderId}
            onChange={(e) => setOrderId(e.target.value)}
            error={errors.order}
          />
        </div>
        <Field
          id="ship-tracking"
          label="Tracking number"
          value={tracking}
          onChange={(e) => setTracking(e.target.value)}
          error={errors.tracking}
        />
        <Field
          id="ship-carrier"
          label="Carrier name"
          value={carrier}
          onChange={(e) => setCarrier(e.target.value)}
          error={errors.carrier}
        />
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <label
            htmlFor="ship-profile"
            className="text-[11px] font-bold uppercase tracking-[0.14em] text-dim"
          >
            Outcome profile
          </label>
          <select
            id="ship-profile"
            value={profile}
            onChange={(e) => setProfile(e.target.value as typeof profile)}
            className="h-12 border-2 border-line-strong bg-panel px-3 text-base text-fg"
          >
            {OUTCOME_PROFILES.map((p) => (
              <option key={p} value={p}>
                {p.replace(/_/g, " ").toLowerCase()}
              </option>
            ))}
          </select>
          <p className="text-xs text-dim">
            outcome_profile scripts the simulated carrier for the demo. It is labelled simulated
            everywhere buyers see it.
          </p>
        </div>
        <div className="sm:col-span-2">
          <Button type="submit" size="lg" disabled={busy}>
            {busy ? "Marking…" : "Mark shipped"}
          </Button>
        </div>
      </form>
      {done && (
        <Notice tone="ok" title="Marked shipped">
          <p>
            Shipment {shortId(done.id, 6)} · promised {formatDate(done.promised_at_sim)} ·{" "}
            {done.carrier_label ?? SIMULATED_CARRIER_LABEL}
          </p>
        </Notice>
      )}
      {failure !== null && <ApiErrorNotice error={failure} />}
    </section>
  );
}

export function MerchantDesk() {
  const [orderId, setOrderId] = React.useState("");
  return (
    <div className="flex flex-col gap-12 pb-12">
      <Queue />
      <div className="grid gap-12 xl:grid-cols-2">
        <OrdersLookup onPick={setOrderId} />
        <ShipForm orderId={orderId} setOrderId={setOrderId} />
      </div>
    </div>
  );
}
