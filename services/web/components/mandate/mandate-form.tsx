"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";

import { ApiErrorNotice } from "@/components/shared/api-error";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { Slab } from "@/components/ui/slab";
import { Tag } from "@/components/ui/tag";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/api/errors";
import { newIdempotencyKey } from "@/lib/api/ids";
import type { MandatePreview } from "@/lib/api/schemas/mandate";
import { merchantLabel } from "@/lib/format/label";
import { keys, useCatalogMerchants } from "@/lib/hooks/queries";
import {
  INTENT_MAX,
  SERVER_FIELD_TO_FORM,
  buildTerms,
  defaultFormState,
  type FormErrors,
  type MandateFormState,
} from "@/lib/mandate/build-terms";
import { cn } from "@/lib/utils";

interface PreviewState {
  data: MandatePreview;
  /** The form as it was when previewed. Any change makes the preview stale. */
  snapshot: string;
  /** One idempotency key per preview, reused only if the sign call is retried. */
  key: string;
}

function useNow(intervalMs = 1000): number {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

function clock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function shortHash(h: string): string {
  return h.length > 12 ? `${h.slice(0, 6)}…${h.slice(-4)}` : h;
}

function Check({
  id,
  checked,
  onChange,
  label,
  sub,
}: {
  id: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  sub?: string;
}) {
  return (
    <label
      htmlFor={id}
      className={cn(
        "flex cursor-pointer items-center gap-3 border-2 px-3.5 py-3",
        checked ? "border-seal bg-seal-soft" : "border-line-strong bg-panel",
      )}
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-5 w-5 accent-[var(--seal)]"
      />
      <span>
        <span className="block font-semibold">{label}</span>
        {sub && <span className="block font-mono text-xs text-dim">{sub}</span>}
      </span>
    </label>
  );
}

function Section({ n, title, children }: { n: string; title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-4 border-t-4 border-fg pt-3">
      <h2 className="text-xs font-bold uppercase tracking-[0.16em] text-dim">
        {n} · {title}
      </h2>
      {children}
    </section>
  );
}

/** Preview, read the exact text, then sign that text. */
export function MandateForm() {
  const router = useRouter();
  const qc = useQueryClient();
  const catalog = useCatalogMerchants();
  const [form, setForm] = React.useState<MandateFormState | null>(null);
  const [errors, setErrors] = React.useState<FormErrors>({});
  const [preview, setPreview] = React.useState<PreviewState | null>(null);
  const [busy, setBusy] = React.useState<"preview" | "sign" | null>(null);
  const [failure, setFailure] = React.useState<unknown>(null);
  const [refreshed, setRefreshed] = React.useState(false);
  const now = useNow();

  // The default end date depends on the clock, so it is set after mount.
  React.useEffect(() => setForm(defaultFormState()), []);

  const merchantIds = React.useMemo(() => {
    const ids = new Set<string>();
    for (const item of catalog.data?.items ?? []) if (item.active) ids.add(item.merchant_id);
    return Array.from(ids).sort();
  }, [catalog.data]);

  if (!form) return <Skeleton className="h-96 w-full" />;

  const set = <K extends keyof MandateFormState>(key: K, value: MandateFormState[K]) => {
    setForm({ ...form, [key]: value });
    setErrors((e) => ({ ...e, [key]: undefined }));
  };

  const built = buildTerms(form);
  const snapshot = JSON.stringify(built.terms ?? form);
  const fresh =
    preview !== null &&
    preview.snapshot === snapshot &&
    new Date(preview.data.nonce_expires_at).getTime() > now;
  const msLeft = preview ? new Date(preview.data.nonce_expires_at).getTime() - now : 0;

  async function runPreview() {
    setFailure(null);
    setRefreshed(false);
    const result = buildTerms(form as MandateFormState);
    if (result.errors) {
      setErrors(result.errors);
      return;
    }
    setBusy("preview");
    try {
      const data = await api.mandate.preview(result.terms);
      setPreview({ data, snapshot: JSON.stringify(result.terms), key: newIdempotencyKey() });
    } catch (e) {
      setPreview(null);
      if (e instanceof ApiError && e.field && SERVER_FIELD_TO_FORM[e.field]) {
        const target = SERVER_FIELD_TO_FORM[e.field] as keyof MandateFormState;
        setErrors({ [target]: e.message });
      } else {
        setFailure(e);
      }
    } finally {
      setBusy(null);
    }
  }

  async function sign() {
    if (!preview || !fresh) return;
    setFailure(null);
    setBusy("sign");
    try {
      const mandate = await api.mandate.sign(
        {
          terms: preview.data.normalized_terms,
          screen_text_hash: preview.data.screen_text_hash,
          nonce: preview.data.nonce,
        },
        { idempotencyKey: preview.key },
      );
      await qc.invalidateQueries({ queryKey: keys.buyerHome });
      router.push(`/mandate/${mandate.mandate_id}`);
    } catch (e) {
      if (
        e instanceof ApiError &&
        (e.code === "NONCE_INVALID" || e.code === "SCREEN_TEXT_MISMATCH")
      ) {
        setPreview(null);
        setRefreshed(true);
      } else {
        setFailure(e);
      }
      setBusy(null);
    }
  }

  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <form
        className="flex flex-col gap-10"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          void runPreview();
        }}
      >
        <Section n="01" title="Spend limits">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              id="cap"
              label="Total cap (USD)"
              inputMode="decimal"
              value={form.cap}
              onChange={(e) => set("cap", e.target.value)}
              error={errors.cap}
              hint="Most the agent can spend in total."
            />
            <Field
              id="per-line"
              label="Max per line"
              inputMode="numeric"
              value={form.perLine}
              onChange={(e) => set("perLine", e.target.value)}
              error={errors.perLine}
              hint="Optional. Most of one item in a cart."
            />
            <Field
              id="ends"
              label="Ends"
              type="datetime-local"
              value={form.ends}
              onChange={(e) => set("ends", e.target.value)}
              error={errors.ends}
              hint="Date and time in your zone."
            />
            <Field
              id="currency"
              label="Currency"
              value="USD"
              disabled
              readOnly
              hint="Sandbox supports USD only."
            />
          </div>
        </Section>

        <Section n="02" title="Shop allowlist">
          {catalog.isPending ? (
            <Skeleton className="h-24 w-full" />
          ) : catalog.isError ? (
            <ApiErrorNotice error={catalog.error} onRetry={() => void catalog.refetch()} />
          ) : (
            <fieldset className="grid gap-3 sm:grid-cols-2">
              <legend className="sr-only">Shops the agent may buy from</legend>
              {merchantIds.map((id) => (
                <Check
                  key={id}
                  id={`m-${id}`}
                  checked={form.merchants.includes(id)}
                  onChange={(on) =>
                    set(
                      "merchants",
                      on ? [...form.merchants, id] : form.merchants.filter((m) => m !== id),
                    )
                  }
                  label={merchantLabel(id)}
                  sub={id}
                />
              ))}
            </fieldset>
          )}
          {errors.merchants && (
            <p role="alert" className="text-xs font-semibold text-flare">
              {errors.merchants}
            </p>
          )}
          <p className="text-xs text-dim">
            From the seeded demo catalog. Anything not ticked is blocked before you see the cart.
          </p>
        </Section>

        <Section n="03" title="Intent">
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="intent"
              className="text-[11px] font-bold uppercase tracking-[0.14em] text-dim"
            >
              What should the agent buy?
            </label>
            <textarea
              id="intent"
              rows={3}
              maxLength={INTENT_MAX}
              value={form.intent}
              onChange={(e) => set("intent", e.target.value.replace(/[\n\r\t]/g, " "))}
              aria-invalid={errors.intent ? true : undefined}
              aria-describedby="intent-count"
              className={cn(
                "border-2 bg-panel p-3 text-base text-fg",
                errors.intent ? "border-flare" : "border-line-strong focus:border-fg",
              )}
            />
            <p id="intent-count" className="tabular text-right text-xs text-dim">
              {form.intent.length} / {INTENT_MAX}
            </p>
            {errors.intent && (
              <p role="alert" className="text-xs font-semibold text-flare">
                {errors.intent}
              </p>
            )}
          </div>
        </Section>

        <Section n="04" title="Protection terms">
          <fieldset className="grid gap-3 sm:grid-cols-2">
            <legend className="sr-only">Problems covered</legend>
            <Check
              id="k-late"
              checked={form.late}
              onChange={(v) => set("late", v)}
              label="Late"
              sub="LATE"
            />
            <Check
              id="k-lost"
              checked={form.lost}
              onChange={(v) => set("lost", v)}
              label="Lost"
              sub="LOST"
            />
          </fieldset>
          {errors.late && (
            <p role="alert" className="text-xs font-semibold text-flare">
              {errors.late}
            </p>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              id="max-refund"
              label="Max refund (USD)"
              inputMode="decimal"
              value={form.maxRefund}
              onChange={(e) => set("maxRefund", e.target.value)}
              error={errors.maxRefund}
              hint="Merchant-funded via PayPal."
            />
            <Field
              id="deliver-days"
              label="Deliver within (days)"
              inputMode="numeric"
              value={form.deliverDays}
              onChange={(e) => set("deliverDays", e.target.value)}
              error={errors.deliverDays}
              hint="The carrier clock is simulated in the sandbox."
            />
          </div>
        </Section>

        <div className="flex flex-wrap items-center gap-4">
          <Button type="submit" variant="secondary" size="lg" disabled={busy !== null}>
            {busy === "preview" ? "Preparing…" : preview ? "Preview again" : "Preview terms"}
          </Button>
        </div>
      </form>

      <aside className="flex flex-col gap-4 lg:sticky lg:top-6 lg:self-start" aria-live="polite">
        <Slab raised notched className="flex flex-col gap-4">
          <Tag tone={fresh ? "ret" : "dashed"} className="self-start">
            {fresh ? "Ready to sign" : "Awaiting signature"}
          </Tag>
          <p className="text-xs font-bold uppercase tracking-[0.14em] text-dim">
            What you sign · exact text
          </p>
          {preview ? (
            <>
              <p className={cn("whitespace-pre-wrap leading-relaxed", !fresh && "text-dim")}>
                {preview.data.screen_text}
              </p>
              <dl className="tabular border-t border-line text-sm">
                <div className="flex justify-between gap-3 border-b border-line py-2">
                  <dt className="text-dim">screen_text_hash</dt>
                  <dd className="font-mono">{shortHash(preview.data.screen_text_hash)}</dd>
                </div>
                <div className="flex justify-between gap-3 border-b border-line py-2">
                  <dt className="text-dim">render · policy</dt>
                  <dd>
                    {preview.data.render_version} · {preview.data.policy_version}
                  </dd>
                </div>
                <div className="flex justify-between gap-3 py-2">
                  <dt className="text-dim">Signing window</dt>
                  <dd>{msLeft > 0 ? clock(msLeft) : "Expired"}</dd>
                </div>
              </dl>
            </>
          ) : (
            <p className="text-sm text-mute">
              Fill in the form and choose Preview terms. You will see the exact text here before you
              sign it.
            </p>
          )}
          <Button size="lg" disabled={!fresh || busy !== null} onClick={() => void sign()}>
            {busy === "sign" ? "Signing…" : "Sign mandate"}
          </Button>
          <p className="text-xs text-dim">
            Signing sends the hash of this exact text. Change any field and the text, hash and nonce
            are issued again.
          </p>
        </Slab>

        {preview && !fresh && msLeft <= 0 && (
          <Notice tone="warn" title="Signing window ended">
            Preview again to get fresh text and a new window.
          </Notice>
        )}
        {preview && !fresh && msLeft > 0 && (
          <Notice tone="info" title="Form changed">
            The text above is out of date. Preview again before signing.
          </Notice>
        )}
        {refreshed && (
          <Notice tone="warn" title="Terms refreshed">
            The text or the signing window changed. Review the terms again, then sign.
          </Notice>
        )}
        {failure !== null && <ApiErrorNotice error={failure} />}
      </aside>
    </div>
  );
}
