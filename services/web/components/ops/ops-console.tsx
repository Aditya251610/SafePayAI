"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiErrorNotice } from "@/components/shared/api-error";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { Slab } from "@/components/ui/slab";
import { Table, TableWrap, Td, Th } from "@/components/ui/data-table";
import { Tag } from "@/components/ui/tag";
import { api } from "@/lib/api";
import { AmbiguousOutcomeError, ApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format/date";
import { caseKindLabel, caseStateLabel, shortId } from "@/lib/format/label";
import { useOpsStatus } from "@/lib/hooks/queries";
import { SIMULATED_CARRIER_LABEL } from "@/lib/honesty/copy";

/** "unknown" means the flag owner cannot be reached; treat it as frozen. */
export function effectivelyFrozen(value: "true" | "false" | "unknown"): boolean {
  return value !== "false";
}

function FreezePanel({ frozenValue }: { frozenValue: "true" | "false" | "unknown" }) {
  const qc = useQueryClient();
  const frozen = effectivelyFrozen(frozenValue);
  const state = useQuery({
    queryKey: ["refunds-frozen"] as const,
    queryFn: ({ signal }) => api.resolution.refundsFrozen(signal),
    retry: false,
  });
  const [reason, setReason] = React.useState("");
  const [reasonError, setReasonError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [failure, setFailure] = React.useState<unknown>(null);
  const [notice, setNotice] = React.useState<string | null>(null);

  async function apply() {
    setBusy(true);
    setFailure(null);
    setNotice(null);
    try {
      await api.ops.freeze({ frozen: !frozen, reason: reason.trim() });
      setNotice(frozen ? "Refunds are unfrozen. Queued refunds will send." : "Refunds are frozen.");
      setReason("");
    } catch (e) {
      if (e instanceof AmbiguousOutcomeError) {
        setNotice(
          "Checking what happened. The switch may have changed; the status below is re-read.",
        );
      } else {
        setFailure(e);
      }
    } finally {
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["ops-status"] }),
        qc.invalidateQueries({ queryKey: ["refunds-frozen"] }),
      ]);
      setBusy(false);
    }
  }

  function check(): boolean {
    if (!reason.trim()) {
      setReasonError("Say why. The reason is written to the audit log.");
      return false;
    }
    setReasonError(null);
    return true;
  }

  return (
    <Slab raised={frozen} className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-bold uppercase tracking-[0.14em] text-dim">Refunds</p>
        <Tag tone={frozen ? "solid-flare" : "solid-ret"}>
          {frozenValue === "unknown"
            ? "Unknown · treated as frozen"
            : frozen
              ? "Frozen"
              : "Running"}
        </Tag>
      </div>
      <h2 className="font-display text-3xl font-extrabold">
        {frozen ? "Refunds are paused." : "Refunds are running."}
      </h2>
      <p className="text-sm text-mute">
        Accepted offers keep their place and send after unfreeze. Status &quot;unknown&quot; means
        the flag owner is unreachable: treat it as frozen.
      </p>
      {state.data && (
        <dl className="tabular border-t border-line text-sm">
          <div className="flex justify-between gap-3 border-b border-line py-2">
            <dt className="text-dim">Last reason</dt>
            <dd className="text-right">{state.data.reason ?? "—"}</dd>
          </div>
          <div className="flex justify-between gap-3 py-2">
            <dt className="text-dim">Set by</dt>
            <dd>{state.data.set_by ?? "—"}</dd>
          </div>
        </dl>
      )}
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="freeze-reason"
          className="text-[11px] font-bold uppercase tracking-[0.14em] text-dim"
        >
          Reason
        </label>
        <textarea
          id="freeze-reason"
          rows={2}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          aria-invalid={reasonError ? true : undefined}
          className="border-2 border-line-strong bg-panel p-3 text-base text-fg focus:border-fg"
        />
        {reasonError && (
          <p role="alert" className="text-xs font-semibold text-flare">
            {reasonError}
          </p>
        )}
      </div>
      <Dialog>
        <DialogTrigger asChild>
          <Button
            variant={frozen ? "primary" : "danger"}
            size="lg"
            disabled={busy}
            onClick={(e) => {
              if (!check()) e.preventDefault();
            }}
          >
            {frozen ? "Unfreeze refunds" : "Freeze refunds"}
          </Button>
        </DialogTrigger>
        <DialogContent
          title={frozen ? "Unfreeze refunds?" : "Freeze refunds?"}
          description={
            frozen
              ? "Queued refunds will be sent. The change is written to the audit log."
              : "New refunds will queue instead of sending. The change is written to the audit log."
          }
        >
          <div className="flex flex-wrap gap-3">
            <DialogClose asChild>
              <Button disabled={busy} onClick={() => void apply()}>
                Yes, {frozen ? "unfreeze" : "freeze"}
              </Button>
            </DialogClose>
            <DialogClose asChild>
              <Button variant="secondary">Cancel</Button>
            </DialogClose>
          </div>
        </DialogContent>
      </Dialog>
      {notice && (
        <Notice tone="info" title="Done">
          {notice}
        </Notice>
      )}
      {failure !== null && <ApiErrorNotice error={failure} />}
    </Slab>
  );
}

function CaseList() {
  const q = useQuery({
    queryKey: ["ops-cases"] as const,
    queryFn: ({ signal }) => api.resolution.cases({}, signal),
    retry: false,
  });
  return (
    <section aria-labelledby="cases-h" className="flex flex-col gap-3">
      <h2 id="cases-h" className="border-t-4 border-fg pt-3 text-xl font-semibold">
        Cases
      </h2>
      {q.isPending ? (
        <Skeleton className="h-24 w-full" />
      ) : q.isError ? (
        <ApiErrorNotice error={q.error} onRetry={() => void q.refetch()} />
      ) : q.data.items.length === 0 ? (
        <Slab>
          <p className="text-sm text-mute">No cases.</p>
        </Slab>
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Case</Th>
                <Th>Kind</Th>
                <Th>Order</Th>
                <Th>State</Th>
              </tr>
            </thead>
            <tbody>
              {q.data.items.map((c) => (
                <tr key={c.case_id}>
                  <Td className="font-mono">CSE-{shortId(c.case_id, 6)}</Td>
                  <Td>{caseKindLabel(c.kind)}</Td>
                  <Td className="font-mono">ORD-{shortId(c.order_id, 6)}</Td>
                  <Td>
                    <Tag>{caseStateLabel(c.state)}</Tag>
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

const DAY = 86_400;

function DemoClock() {
  const qc = useQueryClient();
  const clock = useQuery({
    queryKey: ["demo-clock"] as const,
    queryFn: ({ signal }) => api.tracking.demoClock(signal),
    retry: false,
  });
  const [busy, setBusy] = React.useState<string | null>(null);
  const [failure, setFailure] = React.useState<unknown>(null);

  // A 404 means demo mode is off at the gateway. Remove the whole panel.
  if (clock.isError && clock.error instanceof ApiError && clock.error.status === 404) return null;

  async function run(label: string, call: () => Promise<unknown>) {
    setBusy(label);
    setFailure(null);
    try {
      await call();
      await qc.invalidateQueries({ queryKey: ["demo-clock"] });
    } catch (e) {
      setFailure(e);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Slab className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-bold uppercase tracking-[0.14em] text-dim">
          Demo clock · simulated time
        </p>
        <Tag tone="dashed">Demo mode only</Tag>
      </div>
      {clock.isPending ? (
        <Skeleton className="h-10 w-full" />
      ) : clock.isError ? (
        <ApiErrorNotice error={clock.error} onRetry={() => void clock.refetch()} />
      ) : (
        <p className="tabular font-display text-3xl font-extrabold">
          {formatDateTime(clock.data.sim_now)}
        </p>
      )}
      <p className="text-xs text-dim">
        sim_now. Carrier events fire against this clock, not the real one. {SIMULATED_CARRIER_LABEL}
        .
      </p>
      <div className="flex flex-wrap gap-3">
        <Button
          variant="secondary"
          disabled={busy !== null}
          onClick={() =>
            void run("day", () =>
              api.tracking.advanceClock({ delta_seconds: DAY, reason: "Demo: advance one day" }),
            )
          }
        >
          +1 day
        </Button>
        <Button
          variant="secondary"
          disabled={busy !== null}
          onClick={() =>
            void run("week", () =>
              api.tracking.advanceClock({
                delta_seconds: 7 * DAY,
                reason: "Demo: advance one week",
              }),
            )
          }
        >
          +7 days
        </Button>
        <Button
          variant="ghost"
          disabled={busy !== null}
          onClick={() => void run("reset", () => api.tracking.resetClock())}
        >
          Reset
        </Button>
      </div>
      {failure !== null && <ApiErrorNotice error={failure} />}
    </Slab>
  );
}

export function OpsConsole() {
  const status = useOpsStatus();

  if (status.isPending) return <Skeleton className="h-64 w-full" />;
  if (status.isError)
    return <ApiErrorNotice error={status.error} onRetry={() => void status.refetch()} />;

  const s = status.data;
  return (
    <div className="flex flex-col gap-10 pb-12">
      <div className="flex flex-wrap items-center gap-3">
        <Tag tone={s.money_routes_enabled ? "ret" : "solid-flare"}>
          Money routes {s.money_routes_enabled ? "on" : "off"}
        </Tag>
        <Tag tone={s.demo_mode ? "seal" : "neutral"}>Demo mode {s.demo_mode ? "on" : "off"}</Tag>
        <span className="font-mono text-xs text-dim">build {s.build_id}</span>
        <Link
          href="/audit"
          className="ml-auto text-sm font-semibold text-seal underline-offset-4 hover:underline"
        >
          View audit log
        </Link>
      </div>
      <div className="grid gap-8 lg:grid-cols-2">
        <FreezePanel frozenValue={s.refunds_frozen} />
        <div className="flex flex-col gap-8">
          {s.demo_mode && <DemoClock />}
          <Slab className="flex flex-col gap-2">
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-dim">Cron tick</p>
            <p className="text-sm text-mute">
              The detector and reconcile ticks run from a scheduled job with its own secret, not
              from a session. There is no button here.
            </p>
          </Slab>
        </div>
      </div>
      <CaseList />
    </div>
  );
}
