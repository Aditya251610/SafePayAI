"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";

import { ApiErrorNotice } from "@/components/shared/api-error";
import { WakingUp } from "@/components/shared/waking-up";
import { Button } from "@/components/ui/button";
import { CaseRail } from "@/components/ui/case-rail";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { Slab } from "@/components/ui/slab";
import { Tag } from "@/components/ui/tag";
import { api } from "@/lib/api";
import { AmbiguousOutcomeError, ApiError } from "@/lib/api/errors";
import { newIdempotencyKey } from "@/lib/api/ids";
import type { Offer } from "@/lib/api/schemas/resolution";
import { formatDateTime } from "@/lib/format/date";
import { caseKindLabel, caseStateLabel, shortId } from "@/lib/format/label";
import { formatMoney } from "@/lib/format/money";
import { useCase } from "@/lib/hooks/queries";
import { loadReport } from "@/lib/storage/entries";

type Decline = "NOT_WANTED" | "WANT_HUMAN" | "OTHER";

const DECLINE_LABEL: Record<Decline, string> = {
  NOT_WANTED: "I do not want this",
  WANT_HUMAN: "I want a person to look",
  OTHER: "Something else",
};

interface Result {
  title: string;
  text: string;
  tone: "ok" | "info" | "warn";
}

/** What the buyer should read after accepting, by the server's execution and refund fields. */
export function acceptResult(execution: string, refundStatus: string | null | undefined): Result {
  if (refundStatus === "FAILED") {
    return {
      tone: "warn",
      title: "Refund did not go through.",
      text: "PayPal refused the refund. A person will look. You do not need to do anything.",
    };
  }
  if (execution === "QUEUED_FROZEN") {
    return {
      tone: "info",
      title: "Refund queued. Refunds are paused.",
      text: "You accepted. An operator froze refunds. It sends when they unfreeze. Nothing is lost.",
    };
  }
  if (execution === "DONE") {
    return {
      tone: "ok",
      title: "Refund sent.",
      text: "The refund went out. It is merchant-funded via PayPal.",
    };
  }
  return {
    tone: "info",
    title: "Refund in progress.",
    text: "You accepted. The refund is being sent. This page updates on its own.",
  };
}

function OfferCard({
  offer,
  caseId,
  onDone,
}: {
  offer: Offer;
  caseId: string;
  onDone: (r: Result) => void;
}) {
  const qc = useQueryClient();
  const [reason, setReason] = React.useState<Decline>("NOT_WANTED");
  const [busy, setBusy] = React.useState<"accept" | "decline" | null>(null);
  const [failure, setFailure] = React.useState<unknown>(null);
  const acceptKey = React.useRef<string | null>(null);
  const declineKey = React.useRef<string | null>(null);

  const refresh = () => qc.invalidateQueries({ queryKey: ["case", caseId] });

  async function accept() {
    setBusy("accept");
    setFailure(null);
    acceptKey.current ??= newIdempotencyKey();
    try {
      const r = await api.resolution.acceptOffer(offer.offer_id, offer.proposal_hash, {
        idempotencyKey: acceptKey.current,
      });
      onDone(acceptResult(r.execution, r.refund?.status));
      await refresh();
    } catch (e) {
      if (e instanceof AmbiguousOutcomeError) {
        // The refund may already be moving. Read the case; never post again.
        onDone({
          tone: "info",
          title: "Checking what happened.",
          text: "The request may have gone through. We are reading the case. Do not accept twice.",
        });
        await refresh();
      } else {
        setFailure(e);
      }
    } finally {
      setBusy(null);
    }
  }

  async function decline() {
    setBusy("decline");
    setFailure(null);
    declineKey.current ??= newIdempotencyKey();
    try {
      await api.resolution.declineOffer(offer.offer_id, reason, {
        idempotencyKey: declineKey.current,
      });
      onDone({
        tone: "info",
        title: "You declined the offer.",
        text:
          reason === "WANT_HUMAN"
            ? "Reason recorded. The case moves to a reviewer."
            : "Reason recorded.",
      });
      await refresh();
    } catch (e) {
      setFailure(e);
    } finally {
      setBusy(null);
    }
  }

  const needsLink = offer.tier === "APPROVE";
  const review = offer.tier === "REVIEW";
  const label = offer.action === "RESHIP" ? "Reship" : "Refund";

  return (
    <Slab raised notched className="flex flex-col gap-4">
      <p className="text-xs font-bold uppercase tracking-[0.14em] text-flare">Offer</p>
      <h2 className="font-display text-4xl font-extrabold leading-tight">
        {label} {offer.action === "REFUND" ? formatMoney(offer.amount_minor, offer.currency) : ""}
      </h2>
      <p className="text-sm text-mute">
        Rules drafted this offer from the order, the carrier record and your mandate terms. The
        amount is the server&apos;s. Refunds are merchant-funded via PayPal.
      </p>

      {needsLink ? (
        <Notice tone="warn" title="Approval needed">
          Check your email for the approval link. Opening it shows the exact refund before you
          consent.
        </Notice>
      ) : review ? (
        <Notice tone="info" title="A person is reviewing this case.">
          Nothing is decided yet.
        </Notice>
      ) : (
        <div className="flex flex-col gap-4">
          <Button size="lg" disabled={busy !== null} onClick={() => void accept()}>
            {busy === "accept" ? "Accepting…" : "Accept offer"}
          </Button>
          <div className="flex flex-col gap-1.5 border-t border-line pt-4">
            <label
              htmlFor="decline-reason"
              className="text-[11px] font-bold uppercase tracking-[0.14em] text-dim"
            >
              Or decline, and say why
            </label>
            <select
              id="decline-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value as Decline)}
              className="h-12 border-2 border-line-strong bg-panel px-3 text-base text-fg"
            >
              {(Object.keys(DECLINE_LABEL) as Decline[]).map((k) => (
                <option key={k} value={k}>
                  {DECLINE_LABEL[k]}
                </option>
              ))}
            </select>
            <Button variant="secondary" disabled={busy !== null} onClick={() => void decline()}>
              {busy === "decline" ? "Declining…" : "Decline offer"}
            </Button>
          </div>
        </div>
      )}
      {failure !== null && (
        <ApiErrorNotice
          error={failure}
          onRetry={
            failure instanceof ApiError && failure.code === "OFFER_NOT_ACTIVE"
              ? () => void refresh()
              : undefined
          }
        />
      )}
    </Slab>
  );
}

const STATE_NOTE: Record<string, { title: string; text: string }> = {
  HUMAN_REVIEW: {
    title: "A person is reviewing this case.",
    text: "Nothing is decided yet. No amount is shown until a person has looked.",
  },
  DECLINED: { title: "You declined the offer.", text: "Reason recorded." },
  REFUNDING: {
    title: "Refund in progress.",
    text: "The refund is being sent. This page updates on its own.",
  },
  APPROVED: { title: "Approved.", text: "The refund is about to be sent." },
  RESOLVED_REFUNDED: { title: "Refund sent.", text: "Merchant-funded via PayPal." },
  RESOLVED_RESHIP: { title: "Reshipping.", text: "The shop is sending the order again." },
  CLOSED: { title: "This case is closed.", text: "Nothing more is needed." },
};

export function CaseView() {
  const { id } = useParams<{ id: string }>();
  const kase = useCase(id);
  const [saved, setSaved] = React.useState<ReturnType<typeof loadReport>>(null);
  const [result, setResult] = React.useState<Result | null>(null);
  React.useEffect(() => setSaved(loadReport(id)), [id]);

  if (kase.isPending) {
    return (
      <div className="flex flex-col gap-4 py-8" aria-busy="true">
        <Skeleton className="h-16 w-80" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }
  if (kase.isError) {
    return kase.error instanceof ApiError && kase.error.code === "UPSTREAM_WAKING" ? (
      <WakingUp />
    ) : (
      <ApiErrorNotice error={kase.error} onRetry={() => void kase.refetch()} />
    );
  }

  const c = kase.data;
  const offer = saved?.offer && saved.offer.status === "ACTIVE" ? saved.offer : null;
  const offerOpen = c.state === "OFFERED" && offer !== null && result === null;
  const note = STATE_NOTE[c.state];

  return (
    <div className="pb-12">
      <div className="flex flex-wrap items-end justify-between gap-6 pb-8 pt-10 md:pt-12">
        <div>
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.16em] text-seal">
            /cases/CSE-{shortId(c.case_id, 6)}
          </p>
          <h1 className="mt-3 font-display text-5xl font-black leading-[0.92] tracking-tight md:text-7xl">
            {caseKindLabel(c.kind)}.
            <br />
            <span className="italic text-seal">{caseStateLabel(c.state)}.</span>
          </h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <Tag tone="flare">{caseStateLabel(c.state)}</Tag>
          <Tag>{caseKindLabel(c.kind)}</Tag>
        </div>
      </div>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="flex min-w-0 flex-col gap-6">
          <CaseRail state={c.state} />

          {result && (
            <Notice
              tone={result.tone === "warn" ? "warn" : result.tone === "ok" ? "ok" : "info"}
              title={result.title}
            >
              {result.text}
            </Notice>
          )}

          {offerOpen && offer && <OfferCard offer={offer} caseId={c.case_id} onDone={setResult} />}

          {!offerOpen && !result && note && (
            <Notice tone={c.state === "RESOLVED_REFUNDED" ? "ok" : "info"} title={note.title}>
              {note.text}
            </Notice>
          )}

          {c.state === "OFFERED" && !offer && !result && (
            <Notice tone="info" title="The offer is not shown on this screen">
              This browser does not hold the offer for this case. If you were sent an approval link,
              open it. Otherwise the offer cannot be displayed here yet.
            </Notice>
          )}

          {saved?.reasons && saved.reasons.length > 0 && (
            <section aria-labelledby="why-h" className="flex flex-col gap-2">
              <h2 id="why-h" className="border-t-4 border-fg pt-3 text-xl font-semibold">
                Why
              </h2>
              <ul>
                {saved.reasons.map((r) => (
                  <li
                    key={r.code}
                    className="flex justify-between gap-4 border-b border-line py-2 text-sm"
                  >
                    <span>{r.text ?? r.code}</span>
                    <span className="font-mono text-xs text-dim">{r.code}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        <aside className="flex min-w-0 flex-col gap-4">
          <Slab className="flex flex-col gap-3">
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-dim">Case</p>
            <dl className="tabular text-sm">
              <div className="flex justify-between gap-3 border-b border-line py-2">
                <dt className="text-dim">Opened</dt>
                <dd>{formatDateTime(c.opened_at)}</dd>
              </div>
              <div className="flex justify-between gap-3 border-b border-line py-2">
                <dt className="text-dim">Opened by</dt>
                <dd>{c.origin === "DETECTOR" ? "Late detector" : "Your report"}</dd>
              </div>
              <div className="flex justify-between gap-3 py-2">
                <dt className="text-dim">Order</dt>
                <dd>
                  <Link
                    href={`/orders/${c.order_id}`}
                    className="font-mono text-seal underline-offset-4 hover:underline"
                  >
                    ORD-{shortId(c.order_id, 6)}
                  </Link>
                </dd>
              </div>
            </dl>
            {c.window_hold && (
              <p className="text-xs text-dim">
                The claim window is on hold while this case is open.
              </p>
            )}
            <p className="text-xs text-dim">
              Carrier status is simulated. The AI drafts labels; rules decide money.
            </p>
          </Slab>
        </aside>
      </div>
    </div>
  );
}
