"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { ApiErrorNotice } from "@/components/shared/api-error";
import { WakingUp } from "@/components/shared/waking-up";
import { acceptResult } from "@/components/cases/case-view";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { Slab } from "@/components/ui/slab";
import { Tag } from "@/components/ui/tag";
import { api } from "@/lib/api";
import { AmbiguousOutcomeError, ApiError } from "@/lib/api/errors";
import { newIdempotencyKey } from "@/lib/api/ids";
import { formatDateTime } from "@/lib/format/date";
import { shortId } from "@/lib/format/label";
import { formatMoney } from "@/lib/format/money";
import { useApproval } from "@/lib/hooks/queries";

/** The exact refund, shown before the buyer consents. The link is single-use. */
export function ApproveView() {
  const { token } = useParams<{ token: string }>();
  const preview = useApproval(token);
  const [busy, setBusy] = React.useState(false);
  const [failure, setFailure] = React.useState<unknown>(null);
  const [done, setDone] = React.useState<{
    title: string;
    text: string;
    tone: "ok" | "info" | "warn";
  } | null>(null);
  const key = React.useRef<string | null>(null);

  async function consent() {
    if (!preview.data) return;
    setBusy(true);
    setFailure(null);
    key.current ??= newIdempotencyKey();
    try {
      const r = await api.resolution.consent(
        token,
        { proposalHash: preview.data.proposal_hash, csrfNonce: newIdempotencyKey() },
        { idempotencyKey: key.current },
      );
      setDone(acceptResult(r.execution, null));
    } catch (e) {
      if (e instanceof AmbiguousOutcomeError) {
        setDone({
          tone: "info",
          title: "Checking what happened.",
          text: "The request may have gone through. Open the case to see where it stands. Do not consent twice.",
        });
      } else {
        setFailure(e);
      }
    } finally {
      setBusy(false);
    }
  }

  if (preview.isPending) return <Skeleton className="h-64 w-full" />;
  if (preview.isError) {
    return preview.error instanceof ApiError && preview.error.code === "UPSTREAM_WAKING" ? (
      <WakingUp />
    ) : (
      <ApiErrorNotice error={preview.error} />
    );
  }

  const p = preview.data;
  const caseLink = `/cases/${p.case_id}`;

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <Slab raised notched className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <Tag tone="solid-flare">Approval needed</Tag>
          <span className="font-mono text-xs text-dim">CSE-{shortId(p.case_id, 6)}</span>
        </div>
        <h2 className="font-display text-4xl font-extrabold leading-tight">
          {p.action === "RESHIP"
            ? "Reship the order"
            : `Refund ${formatMoney(p.amount_minor, p.currency)}`}
        </h2>
        <p className="text-mute">{p.summary}</p>
        <dl className="tabular border-t border-line text-sm">
          <div className="flex justify-between gap-3 border-b border-line py-2">
            <dt className="text-dim">Funding</dt>
            <dd>Merchant-funded via PayPal</dd>
          </div>
          {p.expires_at && (
            <div className="flex justify-between gap-3 border-b border-line py-2">
              <dt className="text-dim">Link expires</dt>
              <dd>{formatDateTime(p.expires_at)}</dd>
            </div>
          )}
        </dl>
        {done ? (
          <Notice tone={done.tone} title={done.title}>
            {done.text}
          </Notice>
        ) : (
          <Button size="lg" disabled={busy} onClick={() => void consent()}>
            {busy ? "Approving…" : "Approve"}
          </Button>
        )}
        <p className="text-xs text-dim">Only you can approve. This link works once.</p>
      </Slab>
      {failure !== null && <ApiErrorNotice error={failure} />}
      <Button asChild variant="secondary" className="self-start">
        <Link href={caseLink}>Open the case</Link>
      </Button>
    </div>
  );
}
