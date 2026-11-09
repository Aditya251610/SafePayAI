"use client";

import * as React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiErrorNotice } from "@/components/shared/api-error";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { Slab } from "@/components/ui/slab";
import { Table, TableWrap, Td, Th } from "@/components/ui/data-table";
import { Tag } from "@/components/ui/tag";
import { api } from "@/lib/api";
import { AmbiguousOutcomeError, ApiError } from "@/lib/api/errors";
import { newIdempotencyKey } from "@/lib/api/ids";
import {
  REVIEW_DECISIONS,
  REVIEW_NOTE_MAX,
  type ReviewDecision,
  type ReviewDecisionResponse,
  type ReviewQueue as ReviewQueueData,
} from "@/lib/api/schemas/resolution";
import { useSession } from "@/lib/auth/session";
import { cn } from "@/lib/utils";
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
  if (state === "WITHIN") return "seal" as const;
  return "dashed" as const;
}

type QueueItem = ReviewQueueData["items"][number];

const DECISION_COPY: Record<ReviewDecision, { title: string; text: string }> = {
  PROPOSE_REFUND: {
    title: "Propose a refund",
    text: "The rules set the amount. The buyer must approve it by link before anything is sent.",
  },
  PROPOSE_RESHIP: {
    title: "Propose a reship",
    text: "The buyer is asked to approve the shop sending the order again.",
  },
  DECLINE: { title: "Decline", text: "No remedy. The note is kept with the case." },
  CLOSE: { title: "Close", text: "Nothing more is needed. The note is kept with the case." },
};

/** Decision form for one HUMAN_REVIEW case. The person decides; the server applies the rules. */
function DecisionPanel({ item, onClose }: { item: QueueItem; onClose: () => void }) {
  const qc = useQueryClient();
  const { session } = useSession();
  const reviewer =
    session.status === "authenticated"
      ? (session.me.display_name ?? session.me.actor_id)
      : "reviewer";
  const [decision, setDecision] = React.useState<ReviewDecision | null>(null);
  const [note, setNote] = React.useState("");
  const [touched, setTouched] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [failure, setFailure] = React.useState<unknown>(null);
  const [ambiguous, setAmbiguous] = React.useState(false);
  const [done, setDone] = React.useState<ReviewDecisionResponse | null>(null);
  // One key per intent: a retry of the same decision and note reuses it.
  const key = React.useRef<string | null>(null);

  const noteTrimmed = note.trim();
  const noteError =
    touched && noteTrimmed.length < 3 ? "Add a short note (3 or more characters)." : undefined;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!decision || noteTrimmed.length < 3) return;
    setBusy(true);
    setFailure(null);
    setAmbiguous(false);
    key.current ??= newIdempotencyKey();
    try {
      const r = await api.resolution.reviewDecision(
        item.case_id,
        { decision, reviewer_name: reviewer.slice(0, 64), reason: noteTrimmed },
        { idempotencyKey: key.current },
      );
      setDone(r);
      await qc.invalidateQueries({ queryKey: ["review-queue"] });
    } catch (err) {
      if (err instanceof AmbiguousOutcomeError) {
        setAmbiguous(true);
        await qc.invalidateQueries({ queryKey: ["review-queue"] });
      } else {
        setFailure(err);
        if (err instanceof ApiError && err.code === "ILLEGAL_TRANSITION") {
          await qc.invalidateQueries({ queryKey: ["review-queue"] });
        }
      }
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <Notice tone="ok" title="Decision recorded">
        <p>
          CSE-{shortId(done.case_id, 6)} is now {done.state.replace(/_/g, " ").toLowerCase()}.
          {done.offer_id ? " The buyer has been sent an approval link." : ""}
        </p>
        <Button variant="secondary" size="sm" className="mt-3" onClick={onClose}>
          Done
        </Button>
      </Notice>
    );
  }

  return (
    <Slab raised notched className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.16em] text-seal">
          Decide CSE-{shortId(item.case_id, 6)}
        </p>
        <Tag tone="dashed">A person decides</Tag>
      </div>
      <p className="text-sm text-mute">{item.brief}</p>
      <form className="flex flex-col gap-4" onSubmit={(e) => void submit(e)} noValidate>
        <fieldset className="flex flex-col gap-2">
          <legend className="pb-1 text-[11px] font-bold uppercase tracking-[0.14em] text-dim">
            Decision
          </legend>
          {REVIEW_DECISIONS.map((d) => (
            <label
              key={d}
              className={cn(
                "flex cursor-pointer gap-3 border-2 p-3 text-sm",
                decision === d ? "border-fg" : "border-line-strong",
              )}
            >
              <input
                type="radio"
                name="decision"
                value={d}
                checked={decision === d}
                onChange={() => {
                  setDecision(d);
                  key.current = null;
                }}
                className="mt-1 h-4 w-4"
              />
              <span>
                <span className="block font-semibold">{DECISION_COPY[d].title}</span>
                <span className="block text-mute">{DECISION_COPY[d].text}</span>
              </span>
            </label>
          ))}
          {touched && !decision && (
            <p role="alert" className="text-xs font-semibold text-flare">
              Choose a decision.
            </p>
          )}
        </fieldset>
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="review-note"
            className="text-[11px] font-bold uppercase tracking-[0.14em] text-dim"
          >
            Note (required)
          </label>
          <textarea
            id="review-note"
            rows={3}
            maxLength={REVIEW_NOTE_MAX}
            value={note}
            onChange={(e) => {
              setNote(e.target.value);
              key.current = null;
            }}
            aria-invalid={noteError ? true : undefined}
            aria-describedby={noteError ? "review-note-error" : undefined}
            className={cn(
              "border-2 bg-panel px-3 py-2 text-base text-fg",
              noteError ? "border-flare" : "border-line-strong focus:border-fg",
            )}
          />
          {noteError && (
            <p id="review-note-error" role="alert" className="text-xs font-semibold text-flare">
              {noteError}
            </p>
          )}
        </div>
        <p className="text-xs text-dim">
          Recorded as {reviewer}. The decision is written to the audit log.
        </p>
        <div className="flex flex-wrap gap-3">
          <Button type="submit" disabled={busy}>
            {busy ? "Submitting…" : "Submit decision"}
          </Button>
          <Button type="button" variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
        </div>
      </form>
      {ambiguous && (
        <Notice tone="warn" title="Checking what happened">
          The connection dropped. The decision may have been recorded. The queue was re-read: if
          this case is gone from it, the decision went through. Otherwise submit again; the same
          request is safe to repeat.
        </Notice>
      )}
      {failure !== null && <ApiErrorNotice error={failure} />}
    </Slab>
  );
}

export function ReviewQueue() {
  const [selected, setSelected] = React.useState<QueueItem | null>(null);
  const q = useQuery({
    queryKey: ["review-queue"] as const,
    queryFn: ({ signal }) => api.resolution.reviewQueue(signal),
    retry: false,
  });

  return (
    <div className="flex flex-col gap-6 pb-12">
      <Notice tone="info" title="A person decides here">
        Open a case, pick a decision and leave a note. A refund or reship is only proposed: the
        rules set the amount and the buyer approves it before anything is sent.
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
                <Th>
                  <span className="sr-only">Action</span>
                </Th>
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
                  <Td>
                    <Button
                      size="sm"
                      variant="secondary"
                      aria-label={`Open case CSE-${shortId(i.case_id, 6)}`}
                      onClick={() => setSelected(i)}
                    >
                      Open
                    </Button>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </TableWrap>
      )}
      {selected && (
        <DecisionPanel key={selected.case_id} item={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
