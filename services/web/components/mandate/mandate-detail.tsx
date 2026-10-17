"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";

import { mandateTone } from "@/components/domain/mandate-card";
import { ApiErrorNotice } from "@/components/shared/api-error";
import { WakingUp } from "@/components/shared/waking-up";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Meter } from "@/components/ui/meter";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { Slab } from "@/components/ui/slab";
import { Tag } from "@/components/ui/tag";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/api/errors";
import type { RevokeResponse } from "@/lib/api/schemas/mandate";
import { formatDateTime } from "@/lib/format/date";
import { mandateStatusLabel, shortId } from "@/lib/format/label";
import { formatMoney } from "@/lib/format/money";
import { keys, useMandate, useMandateTerms } from "@/lib/hooks/queries";

const REVOKE_REASONS = [
  { value: "CHANGED_MIND", label: "Changed my mind" },
  { value: "SPENDING_TOO_HIGH", label: "Spending is too high" },
  { value: "OTHER", label: "Something else" },
] as const;

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-line py-2.5 text-sm">
      <dt className="text-dim">{k}</dt>
      <dd className="min-w-0 break-words text-right">{v}</dd>
    </div>
  );
}

function RevokePanel({ mandateId }: { mandateId: string }) {
  const qc = useQueryClient();
  const [reason, setReason] = React.useState<string>(REVOKE_REASONS[0].value);
  const [busy, setBusy] = React.useState(false);
  const [failure, setFailure] = React.useState<unknown>(null);
  const [done, setDone] = React.useState<RevokeResponse | null>(null);

  async function revoke() {
    setBusy(true);
    setFailure(null);
    try {
      setDone(await api.mandate.revoke(mandateId, reason));
      await Promise.all([
        qc.invalidateQueries({ queryKey: keys.mandate(mandateId) }),
        qc.invalidateQueries({ queryKey: keys.buyerHome }),
      ]);
    } catch (e) {
      setFailure(e);
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <Notice tone="ok" title="Mandate revoked">
        No new carts will be built. A purchase you already completed keeps its protection.
      </Notice>
    );
  }

  return (
    <Slab className="flex flex-col gap-4">
      <p className="text-xs font-bold uppercase tracking-[0.16em] text-dim">Revoke</p>
      <h3 className="font-display text-3xl font-extrabold">Stop the agent now.</h3>
      <p className="text-sm text-mute">
        No new carts after you revoke. What happens to open orders is set in the terms you signed.
      </p>
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="revoke-reason"
          className="text-[11px] font-bold uppercase tracking-[0.14em] text-dim"
        >
          Reason
        </label>
        <select
          id="revoke-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="h-12 border-2 border-line-strong bg-panel px-3 text-base text-fg"
        >
          {REVOKE_REASONS.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
      </div>
      <Dialog>
        <DialogTrigger asChild>
          <Button variant="danger" size="lg">
            Revoke mandate
          </Button>
        </DialogTrigger>
        <DialogContent
          title="Revoke this mandate?"
          description="The agent loses all authority. This cannot be undone; you would sign a new mandate to shop again."
        >
          <div className="flex flex-wrap gap-3">
            <DialogClose asChild>
              <Button variant="danger" disabled={busy} onClick={() => void revoke()}>
                {busy ? "Revoking…" : "Yes, revoke"}
              </Button>
            </DialogClose>
            <DialogClose asChild>
              <Button variant="secondary">Keep it</Button>
            </DialogClose>
          </div>
        </DialogContent>
      </Dialog>
      {failure !== null && <ApiErrorNotice error={failure} />}
    </Slab>
  );
}

export function MandateDetail() {
  const { id } = useParams<{ id: string }>();
  const mandate = useMandate(id);
  const terms = useMandateTerms(id);

  if (mandate.isPending) {
    return (
      <div className="flex flex-col gap-4 py-12" aria-busy="true">
        <Skeleton className="h-16 w-80" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }
  if (mandate.isError) {
    if (mandate.error instanceof ApiError && mandate.error.code === "UPSTREAM_WAKING") {
      return <WakingUp />;
    }
    return (
      <div className="py-12">
        <ApiErrorNotice error={mandate.error} onRetry={() => void mandate.refetch()} />
      </div>
    );
  }

  const m = mandate.data;
  const active = m.status === "active";

  return (
    <div className="pb-12">
      <div className="flex flex-wrap items-end justify-between gap-6 pb-8 pt-10 md:pt-12">
        <div>
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.16em] text-seal">
            /mandate/MND-{shortId(m.mandate_id, 6)}
          </p>
          <h1 className="mt-3 font-display text-5xl font-black leading-[0.92] tracking-tight md:text-7xl">
            Mandate
            <br />
            <span className="italic text-seal">{m.status}.</span>
          </h1>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button asChild size="lg">
            <Link href="/intent">State what you need</Link>
          </Button>
          <Button asChild size="lg" variant="secondary">
            <Link href="/audit">View audit log</Link>
          </Button>
        </div>
      </div>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="flex min-w-0 flex-col gap-8">
          <Slab raised notched className="flex flex-col gap-4">
            <Tag tone={mandateTone(m.status)} className="self-start">
              {mandateStatusLabel(m.status)}
            </Tag>
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-dim">
              Spent under cap
            </p>
            <p className="tabular text-6xl font-semibold tracking-tight">
              {formatMoney(m.spent_minor, m.currency)}
            </p>
            <p className="tabular text-sm text-mute">
              of {formatMoney(m.max_total_minor, m.currency)} ·{" "}
              {formatMoney(m.remaining_minor, m.currency)} left
              {m.reserved_minor > 0 && <> · {formatMoney(m.reserved_minor, m.currency)} held</>}
            </p>
            <Meter
              part={m.spent_minor}
              whole={m.max_total_minor}
              extra={m.reserved_minor}
              label={`Spent ${formatMoney(m.spent_minor, m.currency)} of ${formatMoney(m.max_total_minor, m.currency)}`}
            />
          </Slab>

          <section aria-labelledby="terms-h" className="flex flex-col gap-2">
            <h2 id="terms-h" className="border-t-4 border-fg pt-3 text-xl font-semibold">
              Terms as signed
            </h2>
            <dl className="tabular">
              <Row k="Intent" v={m.intent_text} />
              <Row k="Cap" v={formatMoney(m.max_total_minor, m.currency)} />
              <Row k="Per line" v={m.max_qty_per_line ?? "—"} />
              <Row k="Shops" v={m.merchant_allowlist.map((s) => s.display_name).join(" · ")} />
              <Row k="Ends" v={formatDateTime(m.expires_at)} />
              <Row k="Currency" v={m.currency} />
              {terms.data && (
                <>
                  <Row k="After revoke" v={terms.data.revoke_effect} />
                  <Row k="Integrity" v={terms.data.integrity} />
                  <Row
                    k="Terms hash"
                    v={
                      <span className="font-mono text-xs">
                        {terms.data.terms_hash.slice(0, 16)}…
                      </span>
                    }
                  />
                </>
              )}
            </dl>
          </section>
        </div>

        <div className="flex min-w-0 flex-col gap-8">
          <Slab className="flex flex-col gap-3">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-dim">
              Protection terms
            </p>
            <div className="flex flex-wrap gap-2">
              {m.protection.kinds_covered.map((k) => (
                <Tag key={k} tone="seal">
                  {k === "LATE" ? "Late" : k === "LOST" ? "Lost" : k}
                </Tag>
              ))}
            </div>
            <p className="tabular text-5xl font-semibold tracking-tight">
              {formatMoney(m.protection.max_refund_minor, m.currency)}
            </p>
            <p className="text-sm text-mute">max refund</p>
            <p className="text-sm text-mute">
              Delivery due in {m.protection.deliver_by_days} days of the order. Rules decide each
              case. Refunds are merchant-funded via PayPal. Carrier status is simulated.
            </p>
          </Slab>

          {active ? (
            <RevokePanel mandateId={m.mandate_id} />
          ) : (
            <Notice tone="info" title={mandateStatusLabel(m.status)}>
              {m.status === "revoked"
                ? `Revoked${m.revoked_at ? ` on ${formatDateTime(m.revoked_at)}` : ""}. Purchases already completed keep their protection.`
                : "This mandate can no longer be used for new carts."}
            </Notice>
          )}
        </div>
      </div>
    </div>
  );
}
