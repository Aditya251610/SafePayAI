"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { ApiErrorNotice } from "@/components/shared/api-error";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { Slab } from "@/components/ui/slab";
import { Table, TableWrap, Td, Th } from "@/components/ui/data-table";
import { Tag } from "@/components/ui/tag";
import { api } from "@/lib/api";
import { isUuid } from "@/lib/api/ids";
import type { AuditRow } from "@/lib/api/schemas/audit";
import { formatDateTime } from "@/lib/format/date";
import { shortId } from "@/lib/format/label";

const PAGE = 25;

function VerifyPanel() {
  const v = useQuery({
    queryKey: ["audit-verify"] as const,
    queryFn: ({ signal }) => api.audit.verify(signal),
    retry: false,
  });

  return (
    <Slab raised={v.data?.ok === false} className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs font-bold uppercase tracking-[0.14em] text-dim">Audit chain</p>
        <Button
          size="sm"
          variant="secondary"
          disabled={v.isFetching}
          onClick={() => void v.refetch()}
        >
          {v.isFetching ? "Checking…" : "Verify again"}
        </Button>
      </div>
      {v.isPending ? (
        <Skeleton className="h-16 w-full" />
      ) : v.isError ? (
        <ApiErrorNotice error={v.error} onRetry={() => void v.refetch()} />
      ) : v.data.ok ? (
        <>
          <Tag tone="ret" className="self-start">
            Chain intact
          </Tag>
          <p className="tabular text-sm text-mute">
            Checked {v.data.checked ?? "all"} entries up to #{v.data.head_seq ?? "—"}
            {v.data.algorithm ? ` · ${v.data.algorithm}` : ""}. Each entry carries the hash of the
            one before.
          </p>
          {v.data.head_hash && (
            <p className="break-all font-mono text-xs text-dim">head {v.data.head_hash}</p>
          )}
        </>
      ) : (
        <>
          <Tag tone="solid-flare" className="self-start">
            Chain broken
          </Tag>
          <p className="tabular text-sm text-mute">
            The check failed at entry #{v.data.first_bad_seq ?? "unknown"}
            {v.data.reason ? ` (${v.data.reason})` : ""}.
          </p>
          {v.data.expected && (
            <p className="break-all font-mono text-xs text-dim">expected {v.data.expected}</p>
          )}
          {v.data.found && (
            <p className="break-all font-mono text-xs text-dim">found {v.data.found}</p>
          )}
        </>
      )}
    </Slab>
  );
}

function Refs({ row }: { row: AuditRow }) {
  const refs: [string, string | null | undefined, string | null][] = [
    ["mandate", row.mandate_id, row.mandate_id ? `/mandate/${row.mandate_id}` : null],
    ["order", row.order_id, row.order_id ? `/orders/${row.order_id}` : null],
    ["case", row.case_id, row.case_id ? `/cases/${row.case_id}` : null],
  ];
  const shown = refs.filter(([, id]) => Boolean(id));
  if (shown.length === 0) return <span className="text-dim">—</span>;
  return (
    <span className="flex flex-wrap gap-x-3 gap-y-1">
      {shown.map(([label, id, href]) =>
        isUuid(id) && href ? (
          <Link
            key={label}
            href={href}
            className="font-mono text-xs text-seal underline-offset-4 hover:underline"
          >
            {label} {shortId(id, 6)}
          </Link>
        ) : (
          <span key={label} className="font-mono text-xs">
            {label} {String(id).slice(0, 8)}
          </span>
        ),
      )}
    </span>
  );
}

export function AuditLog() {
  const [eventType, setEventType] = React.useState("");
  const [applied, setApplied] = React.useState("");
  // Cursors of the pages already visited; the last one is the page on screen.
  const [cursors, setCursors] = React.useState<(number | undefined)[]>([undefined]);
  const cursor = cursors[cursors.length - 1];

  const q = useQuery({
    queryKey: ["audit", cursor ?? "head", applied] as const,
    queryFn: ({ signal }) =>
      api.audit.entries(
        { limit: PAGE, before_seq: cursor, event_type: applied || undefined },
        signal,
      ),
    retry: false,
  });

  const rows = q.data?.rows ?? [];
  const oldest = rows.length > 0 ? rows[rows.length - 1]?.seq : undefined;
  const hasOlder = rows.length >= PAGE && oldest !== undefined && oldest > 1;

  return (
    <div className="flex flex-col gap-8 pb-12">
      <VerifyPanel />

      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setApplied(eventType.trim());
          setCursors([undefined]);
        }}
      >
        <div className="w-full sm:w-72">
          <Field
            id="event-type"
            label="Event type"
            value={eventType}
            onChange={(e) => setEventType(e.target.value)}
            hint="Exact type, like order.captured."
          />
        </div>
        <Button type="submit" variant="secondary">
          Filter
        </Button>
        {applied && (
          <Button
            variant="ghost"
            onClick={() => {
              setEventType("");
              setApplied("");
              setCursors([undefined]);
            }}
          >
            Clear
          </Button>
        )}
      </form>

      {q.isPending ? (
        <div className="flex flex-col gap-2" aria-busy="true">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      ) : q.isError ? (
        <ApiErrorNotice error={q.error} onRetry={() => void q.refetch()} />
      ) : rows.length === 0 ? (
        <Slab>
          <p className="text-sm text-mute">
            No entries{applied ? " for that event type" : " yet"}.
          </p>
        </Slab>
      ) : (
        <>
          <p className="tabular text-sm text-dim">
            Showing {rows.length} entries · newest first · log head #{q.data.head_seq}
          </p>
          <TableWrap className="hidden md:block">
            <Table>
              <thead>
                <tr>
                  <Th>#</Th>
                  <Th>Time</Th>
                  <Th>Event</Th>
                  <Th>Actor</Th>
                  <Th>Refs</Th>
                  <Th>Hash</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.seq}>
                    <Td className="font-mono">{r.seq}</Td>
                    <Td className="whitespace-nowrap">{formatDateTime(r.recorded_at)}</Td>
                    <Td>
                      {r.summary}
                      <span className="block font-mono text-xs text-dim">{r.event_type}</span>
                    </Td>
                    <Td>
                      {r.actor_type}
                      <span className="block font-mono text-xs text-dim">
                        {r.actor_id.slice(0, 12)}
                      </span>
                    </Td>
                    <Td>
                      <Refs row={r} />
                    </Td>
                    <Td className="font-mono text-xs">
                      {r.row_hash_short}
                      <span className="block text-dim">← {r.prev_hash_short}</span>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </TableWrap>
          <ul className="flex flex-col gap-3 md:hidden">
            {rows.map((r) => (
              <li key={r.seq}>
                <Slab className="flex flex-col gap-1.5">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="font-mono text-sm">#{r.seq}</span>
                    <span className="tabular text-xs text-dim">
                      {formatDateTime(r.recorded_at)}
                    </span>
                  </div>
                  <p className="font-semibold">{r.summary}</p>
                  <p className="text-xs text-dim">
                    {r.actor_type} · {r.actor_id.slice(0, 12)}
                  </p>
                  <Refs row={r} />
                  <p className="font-mono text-xs text-dim">
                    {r.row_hash_short} ← {r.prev_hash_short}
                  </p>
                </Slab>
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap gap-3">
            <Button
              variant="secondary"
              disabled={cursors.length <= 1}
              onClick={() => setCursors((c) => c.slice(0, -1))}
            >
              Newer
            </Button>
            <Button
              variant="secondary"
              disabled={!hasOlder}
              onClick={() => oldest !== undefined && setCursors((c) => [...c, oldest])}
            >
              Older
            </Button>
          </div>
        </>
      )}
      <p className="max-w-2xl text-xs text-dim">
        Append-only. Actor is always named. Buyers see their own entries. AI model output is logged
        as a draft, never as a decision.
      </p>
    </div>
  );
}
