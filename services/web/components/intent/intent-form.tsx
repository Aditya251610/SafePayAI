"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { AgentWorking, WATCHDOG_SECONDS, useElapsed } from "@/components/agent/agent-working";
import { ApiErrorNotice } from "@/components/shared/api-error";
import { WakingUp } from "@/components/shared/waking-up";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { Slab } from "@/components/ui/slab";
import { Tag } from "@/components/ui/tag";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/api/errors";
import { newIdempotencyKey } from "@/lib/api/ids";
import type { ProposeRequest } from "@/lib/api/schemas/agent";
import { formatDate } from "@/lib/format/date";
import { merchantLabel } from "@/lib/format/label";
import { formatMoney } from "@/lib/format/money";
import { parseMoneyInput } from "@/lib/format/money-input";
import { useBuyerHome, useCatalogMerchants } from "@/lib/hooks/queries";
import { saveProposal } from "@/lib/storage/entries";
import { cn } from "@/lib/utils";

const EXAMPLES = ["Desk lamp, under $60", "USB-C dock, any brand", "Replacement cable, 2 m"];
const INTENT_MAX = 500;

type Mode = "intent" | "form";

/** Ask the agent for a cart, in words or with a short form. The agent answers with a cart, not a chat. */
export function IntentForm({ initialMode = "intent" }: { initialMode?: Mode }) {
  const router = useRouter();
  const home = useBuyerHome();
  const catalog = useCatalogMerchants();

  const [mode, setMode] = React.useState<Mode>(initialMode);
  const [mandateId, setMandateId] = React.useState("");
  const [text, setText] = React.useState("");
  const [category, setCategory] = React.useState("");
  const [budget, setBudget] = React.useState("");
  const [quantity, setQuantity] = React.useState("1");
  const [shop, setShop] = React.useState("");
  const [keywords, setKeywords] = React.useState("");
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({});
  const [pending, setPending] = React.useState(false);
  const [failure, setFailure] = React.useState<unknown>(null);
  const attempt = React.useRef<{ key: string; body: ProposeRequest } | null>(null);
  const seconds = useElapsed(pending);

  const active = (home.data?.mandates ?? []).filter((m) => m.status === "active");
  const selected = active.find((m) => m.mandate_id === mandateId) ?? active[0];

  React.useEffect(() => {
    if (!mandateId && active[0]) setMandateId(active[0].mandate_id);
  }, [mandateId, active]);

  const categories = React.useMemo(() => {
    const set = new Set<string>();
    for (const i of catalog.data?.items ?? []) if (i.active) set.add(i.category_id);
    return Array.from(set).sort();
  }, [catalog.data]);

  async function submit(reuse: boolean) {
    if (!selected) return;
    let body: ProposeRequest;
    if (reuse && attempt.current) {
      body = attempt.current.body;
    } else if (mode === "intent") {
      const t = text.trim();
      if (!t) {
        setFieldErrors({ text: "Say in a few words what you need." });
        return;
      }
      body = { mandate_id: selected.mandate_id, mode: "intent", intent_text: t };
    } else {
      const errs: Record<string, string> = {};
      const max = parseMoneyInput(budget);
      const qty = Number(quantity);
      if (!category) errs.category = "Pick a category.";
      if (max === null || max < 0) errs.budget = "Enter a budget, like 60.00.";
      if (!Number.isInteger(qty) || qty < 1 || qty > 5) errs.quantity = "Use 1 to 5.";
      if (Object.keys(errs).length || max === null) {
        setFieldErrors(errs);
        return;
      }
      body = {
        mandate_id: selected.mandate_id,
        mode: "form",
        form: {
          category,
          max_budget_minor: max,
          quantity: qty,
          merchant_id: shop || null,
          keywords: keywords.trim() || null,
        },
      };
    }
    setFieldErrors({});
    setFailure(null);
    setPending(true);
    // A retry of the same ask reuses the key so the server answers once.
    const key = reuse && attempt.current ? attempt.current.key : newIdempotencyKey();
    attempt.current = { key, body };
    try {
      const proposal = await api.agent.propose(body, { idempotencyKey: key });
      saveProposal({ proposal, mandateId: body.mandate_id });
      router.push(`/agent/${encodeURIComponent(proposal.proposal_id)}`);
    } catch (e) {
      setFailure(e);
      setPending(false);
    }
  }

  if (home.isPending) return <Skeleton className="h-72 w-full" />;
  if (home.isError) {
    return home.error instanceof ApiError && home.error.code === "UPSTREAM_WAKING" ? (
      <WakingUp />
    ) : (
      <ApiErrorNotice error={home.error} onRetry={() => void home.refetch()} />
    );
  }
  if (active.length === 0) {
    return (
      <Slab className="flex max-w-xl flex-col items-start gap-3">
        <p className="font-semibold">You need an active mandate first.</p>
        <p className="text-sm text-mute">
          The agent can only shop inside a mandate you have signed.
        </p>
        <Button asChild>
          <Link href="/mandate/new">Sign a mandate</Link>
        </Button>
      </Slab>
    );
  }

  const waking = failure instanceof ApiError && failure.code === "UPSTREAM_WAKING";

  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="flex min-w-0 flex-col gap-6">
        <div role="tablist" aria-label="How to ask" className="flex gap-2">
          {(["intent", "form"] as const).map((m) => (
            <button
              key={m}
              role="tab"
              type="button"
              aria-selected={mode === m}
              onClick={() => {
                setMode(m);
                setFieldErrors({});
                setFailure(null);
              }}
              className={cn(
                "h-12 border-2 px-4 text-xs font-bold uppercase tracking-[0.1em] md:h-10",
                mode === m ? "border-fg text-fg" : "border-line-strong text-dim hover:text-fg",
              )}
            >
              {m === "intent" ? "Say it" : "Use a form"}
            </button>
          ))}
        </div>

        {active.length > 1 && (
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="mandate"
              className="text-[11px] font-bold uppercase tracking-[0.14em] text-dim"
            >
              Mandate
            </label>
            <select
              id="mandate"
              value={selected?.mandate_id ?? ""}
              onChange={(e) => setMandateId(e.target.value)}
              className="h-12 border-2 border-line-strong bg-panel px-3 text-base text-fg"
            >
              {active.map((m) => (
                <option key={m.mandate_id} value={m.mandate_id}>
                  {m.intent_text}
                </option>
              ))}
            </select>
          </div>
        )}

        <form
          className="flex flex-col gap-5"
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            void submit(false);
          }}
        >
          {mode === "intent" ? (
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="intent"
                className="text-[11px] font-bold uppercase tracking-[0.14em] text-dim"
              >
                What do you need?
              </label>
              <textarea
                id="intent"
                rows={4}
                maxLength={INTENT_MAX}
                value={text}
                onChange={(e) => setText(e.target.value)}
                aria-invalid={fieldErrors.text ? true : undefined}
                aria-describedby="intent-help"
                className={cn(
                  "border-2 bg-panel p-3 text-base text-fg",
                  fieldErrors.text ? "border-flare" : "border-line-strong focus:border-fg",
                )}
              />
              <p id="intent-help" className="text-xs text-dim">
                This is not a chat. The agent answers with a cart, not a conversation.
              </p>
              {fieldErrors.text && (
                <p role="alert" className="text-xs font-semibold text-flare">
                  {fieldErrors.text}
                </p>
              )}
              <div className="flex flex-wrap gap-2 pt-1">
                {EXAMPLES.map((ex) => (
                  <button
                    key={ex}
                    type="button"
                    onClick={() => setText(ex)}
                    className="h-12 border-2 border-line-strong px-3 text-xs text-mute hover:border-fg hover:text-fg md:h-9"
                  >
                    {ex}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <label
                  htmlFor="category"
                  className="text-[11px] font-bold uppercase tracking-[0.14em] text-dim"
                >
                  Category
                </label>
                <select
                  id="category"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  aria-invalid={fieldErrors.category ? true : undefined}
                  className="h-12 border-2 border-line-strong bg-panel px-3 text-base text-fg"
                >
                  <option value="">Choose…</option>
                  {categories.map((c) => (
                    <option key={c} value={c}>
                      {merchantLabel(c)}
                    </option>
                  ))}
                </select>
                {fieldErrors.category && (
                  <p role="alert" className="text-xs font-semibold text-flare">
                    {fieldErrors.category}
                  </p>
                )}
              </div>
              <Field
                id="budget"
                label="Budget (USD)"
                inputMode="decimal"
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
                error={fieldErrors.budget}
              />
              <Field
                id="quantity"
                label="Quantity"
                inputMode="numeric"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                error={fieldErrors.quantity}
                hint="1 to 5."
              />
              <div className="flex flex-col gap-1.5">
                <label
                  htmlFor="shop"
                  className="text-[11px] font-bold uppercase tracking-[0.14em] text-dim"
                >
                  Shop (optional)
                </label>
                <select
                  id="shop"
                  value={shop}
                  onChange={(e) => setShop(e.target.value)}
                  className="h-12 border-2 border-line-strong bg-panel px-3 text-base text-fg"
                >
                  <option value="">Any shop in the mandate</option>
                  {(selected?.merchant_allowlist ?? []).map((m) => (
                    <option key={m.merchant_id} value={m.merchant_id}>
                      {m.display_name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="sm:col-span-2">
                <Field
                  id="keywords"
                  label="Keywords (optional)"
                  value={keywords}
                  onChange={(e) => setKeywords(e.target.value)}
                />
              </div>
            </div>
          )}

          {pending ? (
            <AgentWorking
              seconds={seconds}
              onRetry={seconds >= WATCHDOG_SECONDS ? () => void submit(true) : undefined}
            />
          ) : (
            <Button type="submit" size="lg" className="self-start">
              Propose cart
            </Button>
          )}
        </form>

        {waking ? (
          <WakingUp />
        ) : failure !== null ? (
          <ApiErrorNotice error={failure} onRetry={() => void submit(true)} />
        ) : null}
      </div>

      <aside className="flex flex-col gap-4">
        <Slab className="flex flex-col gap-3">
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-dim">Agent boundary</p>
          <dl className="tabular text-sm">
            <div className="flex justify-between gap-3 border-b border-line py-2">
              <dt className="text-dim">Shops</dt>
              <dd className="text-right">
                {selected?.merchant_allowlist.map((m) => m.display_name).join(", ")}
              </dd>
            </div>
            <div className="flex justify-between gap-3 border-b border-line py-2">
              <dt className="text-dim">Cap left</dt>
              <dd>{selected ? formatMoney(selected.remaining_minor, selected.currency) : "—"}</dd>
            </div>
            <div className="flex justify-between gap-3 py-2">
              <dt className="text-dim">Ends</dt>
              <dd>{selected ? formatDate(selected.expires_at) : "—"}</dd>
            </div>
          </dl>
        </Slab>
        <Notice tone="info" title="Seeded · not live">
          <Tag tone="dashed" className="mb-2">
            Demo catalog
          </Tag>
          <p>
            Fixed test fixtures. Prices and stock never change. Nothing here is for sale and nothing
            ships.
          </p>
        </Notice>
      </aside>
    </div>
  );
}
