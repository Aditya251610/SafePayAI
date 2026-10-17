"use client";

import { useQuery } from "@tanstack/react-query";

import { ApiErrorNotice } from "@/components/shared/api-error";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { Slab } from "@/components/ui/slab";
import { Table, TableWrap, Td, Th } from "@/components/ui/data-table";
import { Tag } from "@/components/ui/tag";
import { api } from "@/lib/api";
import { caseKindLabel, shortId } from "@/lib/format/label";

/** Age as "3 h 12 min", for display only. */
export function formatAge(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h} h ${m % 60} min`;
  return `${Math.floor(h / 24)} d`;
}

function slaTone(state: string) {
  if (state === "OVER") return "solid-flare" as const;
  if (state === "WITHIN") return "ret" as const;
  return "dashed" as const;
}

export function ReviewQueue() {
  const q = useQuery({
    queryKey: ["review-queue"] as const,
    queryFn: ({ signal }) => api.resolution.reviewQueue(signal),
    retry: false,
  });

  return (
    <div className="flex flex-col gap-6 pb-12">
      <Notice tone="info" title="Read-only in this build">
        The gateway exposes the queue only. Deciding a case (propose a refund or reship, decline, or
        close with a reason) is not available here yet.
      </Notice>
      {q.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : q.isError ? (
        <ApiErrorNotice error={q.error} onRetry={() => void q.refetch()} />
      ) : q.data.items.length === 0 ? (
        <Slab>
          <p className="text-sm text-mute">The queue is empty.</p>
        </Slab>
      ) : (
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th>Case</Th>
                <Th>Kind</Th>
                <Th>Why it is here</Th>
                <Th>Waiting</Th>
                <Th>Target</Th>
                <Th>Brief</Th>
              </tr>
            </thead>
            <tbody>
              {q.data.items.map((i) => (
                <tr key={i.case_id}>
                  <Td className="font-mono">CSE-{shortId(i.case_id, 6)}</Td>
                  <Td>{caseKindLabel(i.kind)}</Td>
                  <Td>
                    <span className="flex flex-wrap gap-1">
                      {i.reason_codes.map((r) => (
                        <Tag key={r}>{r}</Tag>
                      ))}
                    </span>
                  </Td>
                  <Td className="whitespace-nowrap">{formatAge(i.age_s)}</Td>
                  <Td>
                    <Tag tone={slaTone(i.sla_state)}>
                      {i.sla_state.replace(/_/g, " ").toLowerCase()}
                    </Tag>
                  </Td>
                  <Td className="max-w-md">{i.brief}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </TableWrap>
      )}
    </div>
  );
}
