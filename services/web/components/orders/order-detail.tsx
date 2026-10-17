"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { orderTone } from "@/components/orders/orders-list";
import { ApiErrorNotice } from "@/components/shared/api-error";
import { WakingUp } from "@/components/shared/waking-up";
import { Button } from "@/components/ui/button";
import { CaseRail } from "@/components/ui/case-rail";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { Slab } from "@/components/ui/slab";
import { Table, TableWrap, Td, Th } from "@/components/ui/data-table";
import { Tag } from "@/components/ui/tag";
import { ApiError } from "@/lib/api/errors";
import type { Receipt } from "@/lib/api/schemas/checkout";
import { goTo } from "@/lib/checkout/navigate";
import { canRedirectToPayPal } from "@/lib/checkout/outcome";
import { checkLabel, reasonLabel } from "@/lib/format/checks";
import { formatDate, formatDateTime } from "@/lib/format/date";
import { caseKindLabel, caseStateLabel, orderStatusLabel, shortId } from "@/lib/format/label";
import { formatMoney } from "@/lib/format/money";
import { useBffOrder, useReceipt } from "@/lib/hooks/queries";
import { SIMULATED_CARRIER_LABEL } from "@/lib/honesty/copy";
import { cn } from "@/lib/utils";

function ReceiptPanel({ receipt }: { receipt: Receipt }) {
  return (
    <div className="flex flex-col gap-6">
      <Slab className="flex flex-col gap-3">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <p className="text-xs font-bold uppercase tracking-[0.14em] text-dim">Receipt</p>
          <p className="tabular text-4xl font-semibold tracking-tight">
            {formatMoney(receipt.amount_minor, receipt.currency)}
          </p>
        </div>
        <dl className="tabular border-t border-line text-sm">
          {[
            [
              "Capture",
              <span key="c" className="font-mono">
                {receipt.capture_id ?? "—"}
              </span>,
            ],
            [
              "PayPal order",
              <span key="p" className="font-mono">
                {receipt.paypal_order_id ?? "—"}
              </span>,
            ],
            [
              "Mandate",
              <Link
                key="m"
                href={`/mandate/${receipt.mandate.mandate_id}`}
                className="text-seal underline-offset-4 hover:underline"
              >
                MND-{shortId(receipt.mandate.mandate_id, 6)}
              </Link>,
            ],
            ["Protection", `${receipt.protection.window_days} days · ${receipt.protection.label}`],
          ].map(([k, v]) => (
            <div key={String(k)} className="flex justify-between gap-4 border-b border-line py-2">
              <dt className="text-dim">{k}</dt>
              <dd className="min-w-0 break-words text-right">{v}</dd>
            </div>
          ))}
        </dl>
      </Slab>

      <TableWrap>
        <Table>
          <thead>
            <tr>
              <Th>Item</Th>
              <Th className="text-right">Qty</Th>
              <Th className="text-right">Unit</Th>
              <Th className="text-right">Line</Th>
            </tr>
          </thead>
          <tbody>
            {receipt.lines.map((l) => (
              <tr key={l.sku}>
                <Td className="font-mono text-xs">{l.sku}</Td>
                <Td className="text-right">{l.qty}</Td>
                <Td className="text-right">{formatMoney(l.unit_minor, receipt.currency)}</Td>
                <Td className="text-right">{formatMoney(l.line_minor, receipt.currency)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </TableWrap>

      <ul>
        {receipt.checks.map((c) => (
          <li
            key={`${c.name}:${c.reason_code ?? ""}`}
            className="flex justify-between gap-4 border-b border-line py-2 text-sm"
          >
            <span>
              {checkLabel(c.name)}
              {reasonLabel(c.reason_code) && (
                <span className="text-dim"> · {reasonLabel(c.reason_code)}</span>
              )}
            </span>
            <Tag tone={c.result === "PASS" ? "seal" : c.result === "BLOCK" ? "flare" : "dashed"}>
              {c.result}
            </Tag>
          </li>
        ))}
      </ul>

      <ul className="flex flex-col gap-1 text-sm text-mute" aria-label="Disclosures">
        {receipt.disclosures.map((d) => (
          <li key={d}>{d}</li>
        ))}
      </ul>
    </div>
  );
}

export function OrderDetail({
  orderId,
  embedded = false,
}: {
  orderId?: string;
  embedded?: boolean;
}) {
  const params = useParams<{ id: string }>();
  const id = orderId ?? params.id;
  const bff = useBffOrder(id);
  const [tab, setTab] = React.useState<"overview" | "receipt">("overview");
  const captured = bff.data?.order.status === "CAPTURED";
  const receipt = useReceipt(id, captured && tab === "receipt");

  if (bff.isPending) {
    return (
      <div className="flex flex-col gap-4 py-8" aria-busy="true">
        <Skeleton className="h-16 w-80" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }
  if (bff.isError) {
    return bff.error instanceof ApiError && bff.error.code === "UPSTREAM_WAKING" ? (
      <WakingUp />
    ) : (
      <ApiErrorNotice error={bff.error} onRetry={() => void bff.refetch()} />
    );
  }

  const Heading = embedded ? "h2" : "h1";
  const { order, shipment, case: kase, audit_verified: audit } = bff.data;
  const awaiting = order.status === "AWAITING_APPROVAL" && order.approve_url;

  return (
    <div className="pb-12">
      <div
        className={cn(
          "flex flex-wrap items-end justify-between gap-6 pb-8",
          !embedded && "pt-10 md:pt-12",
        )}
      >
        <div>
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.16em] text-seal">
            /orders/ORD-{shortId(order.order_id, 6)}
          </p>
          <Heading
            className={cn(
              "mt-3 font-sans font-semibold leading-[0.92] tracking-tight",
              embedded ? "text-4xl" : "text-5xl md:text-7xl",
            )}
          >
            {formatMoney(order.total_minor, order.currency)}
          </Heading>
          <p className="mt-3 text-mute">
            {(order.item_titles ?? []).join(", ") || "Order"} · {formatDate(order.created_at)}
          </p>
        </div>
        <Tag tone={orderTone(order.status)}>{orderStatusLabel(order.status)}</Tag>
      </div>

      <div role="tablist" aria-label="Order views" className="mb-6 flex gap-2">
        {(["overview", "receipt"] as const).map((t) => (
          <button
            key={t}
            role="tab"
            type="button"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={cn(
              "h-12 border-2 px-4 text-xs font-bold uppercase tracking-[0.1em] md:h-10",
              tab === t ? "border-fg text-fg" : "border-line-strong text-dim hover:text-fg",
            )}
          >
            {t === "overview" ? "Overview" : "Receipt"}
          </button>
        ))}
      </div>

      {tab === "receipt" ? (
        !captured ? (
          <Notice tone="info" title="Receipt is not ready yet.">
            It appears once the payment is captured.
          </Notice>
        ) : receipt.isPending ? (
          <Skeleton className="h-64 w-full" />
        ) : receipt.isError ? (
          <ApiErrorNotice error={receipt.error} onRetry={() => void receipt.refetch()} />
        ) : (
          <ReceiptPanel receipt={receipt.data} />
        )
      ) : (
        <div className={cn("grid gap-8", !embedded && "lg:grid-cols-2")}>
          {awaiting && (
            <div className="lg:col-span-2">
              <Notice tone="warn" title="Payment not finished">
                <p>This order is waiting for your approval at PayPal.</p>
                <div className="mt-3 flex flex-wrap gap-3">
                  <Button
                    size="sm"
                    disabled={!canRedirectToPayPal(order.approve_url ?? "")}
                    onClick={() => order.approve_url && goTo(order.approve_url)}
                  >
                    Continue to PayPal
                  </Button>
                  <Button asChild size="sm" variant="secondary">
                    <Link href="/checkout/return">Check payment</Link>
                  </Button>
                </div>
              </Notice>
            </div>
          )}

          <Slab className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-dim">Tracking</p>
              <Tag tone="dashed">{SIMULATED_CARRIER_LABEL}</Tag>
            </div>
            {shipment === null || shipment === undefined ? (
              <p className="text-sm text-mute">
                Tracking is unavailable. Order and case still load.
              </p>
            ) : shipment.shipments.length === 0 ? (
              <p className="text-sm text-mute">
                No shipment yet. The shop has not marked it shipped.
              </p>
            ) : (
              <>
                {shipment.shipments.map((s) => (
                  <div key={s.id} className="flex flex-wrap items-center gap-2">
                    <Tag tone="seal">{s.status.replace(/_/g, " ")}</Tag>
                    {s.anomaly && (
                      <Tag tone="flare">{s.anomaly.replace(/_/g, " ").toLowerCase()}</Tag>
                    )}
                    <span className="tabular text-sm text-mute">
                      Promised {formatDate(s.promised_at_sim)}
                    </span>
                  </div>
                ))}
                <dl className="tabular border-t border-line text-sm">
                  <div className="flex justify-between border-b border-line py-2">
                    <dt className="text-dim">sim_now</dt>
                    <dd>{formatDateTime(shipment.sim_now)}</dd>
                  </div>
                  {shipment.consistency && (
                    <div className="flex justify-between border-b border-line py-2">
                      <dt className="text-dim">Late or lost</dt>
                      <dd>
                        {shipment.consistency.lost_detected
                          ? "Lost"
                          : shipment.consistency.late_detected
                            ? "Late"
                            : "No"}
                      </dd>
                    </div>
                  )}
                </dl>
                <ol className="text-sm text-mute">
                  {shipment.events.map((e) => (
                    <li
                      key={e.event_id}
                      className="flex justify-between gap-3 border-b border-line py-1.5"
                    >
                      <span>{e.status.replace(/_/g, " ")}</span>
                      <span className="tabular text-dim">{formatDateTime(e.occurred_at_sim)}</span>
                    </li>
                  ))}
                </ol>
              </>
            )}
            <p className="text-xs text-dim">
              Carrier status is simulated. This is not a real shipment.
            </p>
          </Slab>

          <div className="flex flex-col gap-8">
            <Slab raised={Boolean(kase)} className="flex flex-col gap-3">
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-dim">Case</p>
              {kase ? (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <Tag tone="flare">{caseStateLabel(kase.state)}</Tag>
                    <Tag>{caseKindLabel(kase.kind)}</Tag>
                  </div>
                  <CaseRail state={kase.state} />
                  <p className="text-xs text-dim">
                    {kase.origin === "DETECTOR"
                      ? "Opened automatically by the late detector. No form was filed."
                      : "Opened from your report."}
                  </p>
                  <Link
                    href={`/cases/${kase.case_id}`}
                    className="text-sm font-semibold text-seal underline-offset-4 hover:underline"
                  >
                    Open case →
                  </Link>
                </>
              ) : (
                <>
                  <p className="text-sm text-mute">No case. Nothing is wrong with this order.</p>
                  {captured && (
                    <Button asChild variant="secondary" size="sm" className="self-start">
                      <Link href={`/orders/${order.order_id}/report`}>Report a problem</Link>
                    </Button>
                  )}
                </>
              )}
            </Slab>

            <Slab className="flex flex-col gap-2">
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-dim">Audit chain</p>
              {audit === true ? (
                <Tag tone="solid-seal" className="self-start">
                  Chain intact
                </Tag>
              ) : audit === false ? (
                <Tag tone="solid-flare" className="self-start">
                  Chain check failed
                </Tag>
              ) : (
                <Tag tone="dashed" className="self-start">
                  Check unavailable
                </Tag>
              )}
              <p className="text-sm text-mute">
                {audit === null || audit === undefined
                  ? "Chain check unavailable. Try again in a minute."
                  : "Each entry carries the hash of the one before."}
              </p>
              <Link
                href="/audit"
                className="text-sm font-semibold text-seal underline-offset-4 hover:underline"
              >
                View audit log
              </Link>
            </Slab>
          </div>
        </div>
      )}
    </div>
  );
}
