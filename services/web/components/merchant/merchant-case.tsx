"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiErrorNotice } from "@/components/shared/api-error";
import { Button } from "@/components/ui/button";
import { CaseRail } from "@/components/ui/case-rail";
import { Dialog, DialogClose, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { Slab } from "@/components/ui/slab";
import { Tag } from "@/components/ui/tag";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/api/errors";
import { newIdempotencyKey } from "@/lib/api/ids";
import type { MerchantActionResponse } from "@/lib/api/schemas/resolution";
import { formatDateTime } from "@/lib/format/date";
import { caseKindLabel, caseStateLabel, shortId } from "@/lib/format/label";
import { useCase } from "@/lib/hooks/queries";
import { SIMULATED_CARRIER_LABEL } from "@/lib/honesty/copy";

type Action = "OVERRIDE_OFFER" | "CONFIRM_RESHIP";

const ACTIONS: {
  type: Action;
  title: string;
  rule: string;
  note: string;
  allowed: (state: string) => boolean;
}[] = [
  {
    type: "OVERRIDE_OFFER",
    title: "Override the offer",
    rule: "Allowed from OFFERED or DECLINED.",
    note: "Replaces the current offer. The server computes the new amount from the order, the carrier record and the mandate terms.",
    allowed: (s) => s === "OFFERED" || s === "DECLINED",
  },
  {
    type: "CONFIRM_RESHIP",
    title: "Confirm a reship",
    rule: "Allowed from OFFERED when the offer is a reship.",
    note: "You agree to send the order again instead of refunding.",
    allowed: (s) => s === "OFFERED",
  },
];

function ActionCard({
  action,
  caseId,
  state,
  onDone,
}: {
  action: (typeof ACTIONS)[number];
  caseId: string;
  state: string;
  onDone: (r: MerchantActionResponse) => void;
}) {
  const qc = useQueryClient();
  const [busy, setBusy] = React.useState(false);
  const [failure, setFailure] = React.useState<unknown>(null);
  const key = React.useRef<string | null>(null);
  const enabled = action.allowed(state);

  async function run() {
    setBusy(true);
    setFailure(null);
    key.current ??= newIdempotencyKey();
    try {
      onDone(
        await api.resolution.merchantAction(caseId, action.type, { idempotencyKey: key.current }),
      );
      await qc.invalidateQueries({ queryKey: ["case", caseId] });
    } catch (e) {
      setFailure(e);
      if (e instanceof ApiError && e.code === "ILLEGAL_TRANSITION") {
        await qc.invalidateQueries({ queryKey: ["case", caseId] });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Slab className="flex flex-col gap-3">
      <p className="text-xs font-bold uppercase tracking-[0.14em] text-dim">{action.type}</p>
      <h3 className="font-display text-2xl font-extrabold">{action.title}</h3>
      <p className="text-sm text-mute">{action.note}</p>
      <p className="text-xs text-dim">{action.rule}</p>
      <Dialog>
        <DialogTrigger asChild>
          <Button variant="secondary" disabled={!enabled || busy}>
            {action.title}
          </Button>
        </DialogTrigger>
        <DialogContent
          title={`${action.title}?`}
          description="The buyer is told. The case moves forward and the change is written to the audit log."
        >
          <div className="flex flex-wrap gap-3">
            <DialogClose asChild>
              <Button disabled={busy} onClick={() => void run()}>
                Yes, continue
              </Button>
            </DialogClose>
            <DialogClose asChild>
              <Button variant="secondary">Cancel</Button>
            </DialogClose>
          </div>
        </DialogContent>
      </Dialog>
      {failure !== null && <ApiErrorNotice error={failure} />}
    </Slab>
  );
}

export function MerchantCase() {
  const { id } = useParams<{ id: string }>();
  const kase = useCase(id);
  const orderId = kase.data?.order_id;
  const carrier = useQuery({
    queryKey: ["tracking", orderId] as const,
    queryFn: ({ signal }) => api.tracking.forOrder(orderId ?? "", signal),
    enabled: Boolean(orderId),
    retry: false,
  });
  const [result, setResult] = React.useState<MerchantActionResponse | null>(null);

  if (kase.isPending) return <Skeleton className="h-56 w-full" />;
  if (kase.isError)
    return <ApiErrorNotice error={kase.error} onRetry={() => void kase.refetch()} />;

  const c = kase.data;
  const ship = carrier.data?.shipments[0];

  return (
    <div className="flex flex-col gap-8 pb-12">
      <div className="flex flex-wrap items-end justify-between gap-6 pt-2">
        <div>
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.16em] text-seal">
            /merchant/cases/CSE-{shortId(c.case_id, 6)}
          </p>
          <h1 className="mt-3 font-display text-5xl font-black leading-[0.92] tracking-tight md:text-7xl">
            {caseKindLabel(c.kind)}.
            <br />
            <span className="italic text-seal">{caseStateLabel(c.state)}.</span>
          </h1>
        </div>
        <Button asChild variant="secondary">
          <Link href="/merchant">Back to the queue</Link>
        </Button>
      </div>

      <CaseRail state={c.state} />

      <div className="grid gap-8 lg:grid-cols-2">
        <Slab className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-dim">Carrier record</p>
            <Tag tone="dashed">{SIMULATED_CARRIER_LABEL}</Tag>
          </div>
          {carrier.isPending ? (
            <Skeleton className="h-10 w-full" />
          ) : carrier.isError || !ship ? (
            <p className="text-sm text-mute">No shipment on record yet.</p>
          ) : (
            <p className="tabular text-sm text-mute">
              {ship.status.replace(/_/g, " ").toLowerCase()} · promised{" "}
              {formatDateTime(ship.promised_at_sim)}
              {ship.anomaly ? ` · ${ship.anomaly.replace(/_/g, " ").toLowerCase()}` : ""}
            </p>
          )}
          <dl className="tabular border-t border-line text-sm">
            <div className="flex justify-between gap-3 border-b border-line py-2">
              <dt className="text-dim">Opened</dt>
              <dd>{formatDateTime(c.opened_at)}</dd>
            </div>
            <div className="flex justify-between gap-3 py-2">
              <dt className="text-dim">Order</dt>
              <dd className="font-mono">ORD-{shortId(c.order_id, 6)}</dd>
            </div>
          </dl>
        </Slab>

        <Notice tone="info" title="No amount field.">
          You pick an action. The server computes the offer amount from the order, the carrier
          record and the mandate terms. That keeps the number out of anyone&apos;s hands.
        </Notice>
      </div>

      {result && (
        <Notice tone="ok" title="Done">
          The case is now {caseStateLabel(result.state).toLowerCase()}.
        </Notice>
      )}

      <section aria-labelledby="choose-h" className="flex flex-col gap-4">
        <h2 id="choose-h" className="border-t-4 border-fg pt-3 text-xl font-semibold">
          Choose one
        </h2>
        <div className="grid gap-6 lg:grid-cols-2">
          {ACTIONS.map((a) => (
            <ActionCard
              key={a.type}
              action={a}
              caseId={c.case_id}
              state={c.state}
              onDone={setResult}
            />
          ))}
        </div>
      </section>
    </div>
  );
}
