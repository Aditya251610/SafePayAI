"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { ApiErrorNotice } from "@/components/shared/api-error";
import { Button } from "@/components/ui/button";
import { Slab } from "@/components/ui/slab";
import { api } from "@/lib/api";
import { newIdempotencyKey, isUuid } from "@/lib/api/ids";
import { saveReport } from "@/lib/storage/entries";
import { cn } from "@/lib/utils";

const MAX = 4000;

export function OrderReport() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [text, setText] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [failure, setFailure] = React.useState<unknown>(null);
  const key = React.useRef<string | null>(null);

  async function submit() {
    const t = text.trim();
    if (!t) {
      setError("Say what you expected and what you got.");
      return;
    }
    if (!isUuid(id)) {
      setFailure(new Error("bad id"));
      return;
    }
    setError(null);
    setFailure(null);
    setBusy(true);
    key.current ??= newIdempotencyKey();
    try {
      const r = await api.resolution.report(
        { order_id: id, text: t },
        { idempotencyKey: key.current },
      );
      saveReport(r);
      router.push(`/cases/${r.case_id}`);
    } catch (e) {
      setFailure(e);
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="report"
            className="text-[11px] font-bold uppercase tracking-[0.14em] text-dim"
          >
            What went wrong?
          </label>
          <textarea
            id="report"
            rows={6}
            maxLength={MAX}
            value={text}
            onChange={(e) => setText(e.target.value)}
            aria-invalid={error ? true : undefined}
            aria-describedby="report-count"
            className={cn(
              "border-2 bg-panel p-3 text-base text-fg",
              error ? "border-flare" : "border-line-strong focus:border-fg",
            )}
          />
          <p id="report-count" className="tabular text-right text-xs text-dim">
            {text.length} / {MAX}
          </p>
          {error && (
            <p role="alert" className="text-xs font-semibold text-flare">
              {error}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-3">
          <Button type="submit" size="lg" disabled={busy}>
            {busy ? "Opening…" : "Open case"}
          </Button>
          <Button asChild variant="secondary" size="lg">
            <Link href={`/orders/${id}`}>Cancel</Link>
          </Button>
        </div>
        {failure !== null && <ApiErrorNotice error={failure} onRetry={() => void submit()} />}
      </form>

      <Slab className="flex h-fit flex-col gap-3">
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-dim">
          AI reads. Rules decide.
        </p>
        <p className="text-sm text-mute">
          An AI model reads your text and drafts a label: late, lost, damaged, wrong item, not as
          described or other. It cannot offer a refund. The rules do that, using the order, the
          carrier record and your mandate terms.
        </p>
        <p className="text-xs text-dim">
          Carrier status is simulated. Refunds are merchant-funded via PayPal.
        </p>
      </Slab>
    </div>
  );
}
