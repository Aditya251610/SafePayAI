"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { AgentWorking, useElapsed } from "@/components/agent/agent-working";
import { ApiErrorNotice } from "@/components/shared/api-error";
import { ActionBar } from "@/components/ui/action-bar";
import { Button } from "@/components/ui/button";
import { Meter } from "@/components/ui/meter";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { Slab } from "@/components/ui/slab";
import { Table, TableWrap, Td, Th } from "@/components/ui/data-table";
import { Tag } from "@/components/ui/tag";
import { api } from "@/lib/api";
import { AmbiguousOutcomeError } from "@/lib/api/errors";
import { newIdempotencyKey } from "@/lib/api/ids";
import { pollUntil } from "@/lib/api/reconcile";
import type { Check } from "@/lib/api/schemas/common";
import { canRedirectToPayPal } from "@/lib/checkout/outcome";
import { goTo } from "@/lib/checkout/navigate";
import { checkLabel, reasonLabel } from "@/lib/format/checks";
import { merchantLabel, shortId } from "@/lib/format/label";
import { formatMoney } from "@/lib/format/money";
import { useCatalogMerchants, useMandate, useOpsStatus } from "@/lib/hooks/queries";
import { loadCart, saveLastOrder, type CartEntry } from "@/lib/storage/entries";

function checkTone(result: string) {
  if (result === "PASS") return "seal" as const;
  if (result === "BLOCK") return "flare" as const;
  if (result === "TIGHTEN") return "solid" as const;
  return "dashed" as const;
}

function CheckRow({ check }: { check: Check }) {
  const reason = reasonLabel(check.reason_code);
  return (
    <li className="flex items-start justify-between gap-4 border-b border-line py-3">
      <div className="min-w-0">
        <p className="font-semibold">{checkLabel(check.name)}</p>
        <p className="text-xs text-dim">
          {check.source ? `${check.source} · ` : ""}
          {reason ?? "Rule passed"}
        </p>
      </div>
      <Tag tone={checkTone(check.result)}>{check.result}</Tag>
    </li>
  );
}

function CartBody({ entry }: { entry: CartEntry }) {
  const router = useRouter();
  const { cart, mandateId } = entry;
  const mandate = useMandate(mandateId);
  const catalog = useCatalogMerchants();
  const ops = useOpsStatus();

  const [confirmed, setConfirmed] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [failure, setFailure] = React.useState<unknown>(null);
  const [checking, setChecking] = React.useState(false);
  const [blockedLink, setBlockedLink] = React.useState(false);
  const key = React.useRef<string | null>(null);
  const seconds = useElapsed(busy);

  const titles = React.useMemo(() => {
    const m = new Map<string, string>();
    for (const i of catalog.data?.items ?? []) m.set(i.sku, i.title);
    return m;
  }, [catalog.data]);

  const needsConfirm = cart.status === "NEEDS_CONFIRMATION";
  const blocked = cart.status === "BLOCKED";
  const moneyOff = ops.data?.money_routes_enabled === false;
  const merchants = Array.from(new Set(cart.lines.map((l) => merchantLabel(l.merchant_id))));
  const blockers = cart.checks.filter((c) => c.result === "BLOCK");
  const canApprove = !blocked && !moneyOff && !busy && (!needsConfirm || confirmed);

  function toPayPal(orderId: string, approveUrl: string) {
    saveLastOrder(orderId, mandateId);
    if (!canRedirectToPayPal(approveUrl)) {
      setBlockedLink(true);
      setBusy(false);
      return;
    }
    goTo(approveUrl);
  }

  async function approve() {
    setFailure(null);
    setBlockedLink(false);
    setBusy(true);
    key.current ??= newIdempotencyKey();
    try {
      const order = await api.checkout.confirmCart(
        cart.cart_id,
        {
          proposal_hash: cart.proposal_hash,
          confirm_intent_fit: needsConfirm ? confirmed : undefined,
        },
        { idempotencyKey: key.current },
      );
      toPayPal(order.order_id, order.approve_url);
    } catch (e) {
      if (e instanceof AmbiguousOutcomeError) {
        // The order may exist even though the answer was lost. Look for it; do not post again.
        setChecking(true);
        try {
          const found = await pollUntil(
            () => api.checkout.orders({ limit: 5 }),
            (r) => r.items.some((o) => o.cart_id === cart.cart_id),
          );
          const order = found.value.items.find((o) => o.cart_id === cart.cart_id);
          if (order?.approve_url && order.status === "AWAITING_APPROVAL") {
            toPayPal(order.order_id, order.approve_url);
            return;
          }
          if (order) {
            router.push(`/orders/${order.order_id}`);
            return;
          }
        } catch {
          // Fall through to the notice below.
        } finally {
          setChecking(false);
        }
      }
      setFailure(e);
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="flex min-w-0 flex-col gap-8">
        <section aria-labelledby="lines-h" className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2 border-t-4 border-fg pt-3">
            <h2 id="lines-h" className="text-xl font-semibold">
              Cart C-{shortId(cart.cart_id, 4)}
            </h2>
            <Tag tone={blocked ? "flare" : needsConfirm ? "solid-flare" : "solid-ret"}>
              {blocked ? "Blocked" : needsConfirm ? "Needs your confirmation" : "Checked"}
            </Tag>
          </div>
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>Item</Th>
                  <Th className="text-right">Qty</Th>
                  <Th className="text-right">Unit</Th>
                  <Th className="text-right">Line</Th>
                </tr>
              </thead>
              <tbody>
                {cart.lines.length === 0 ? (
                  <tr>
                    <Td colSpan={4} className="text-mute">
                      No lines. The catalog could not price this cart.
                    </Td>
                  </tr>
                ) : (
                  cart.lines.map((l) => (
                    <tr key={l.sku}>
                      <Td>
                        {titles.get(l.sku) ?? l.sku}
                        <span className="block font-mono text-xs text-dim">
                          {l.sku} · {merchantLabel(l.merchant_id)}
                        </span>
                      </Td>
                      <Td className="text-right">{l.qty}</Td>
                      <Td className="text-right">{formatMoney(l.unit_minor, cart.currency)}</Td>
                      <Td className="text-right">{formatMoney(l.line_minor, cart.currency)}</Td>
                    </tr>
                  ))
                )}
                <tr>
                  <Td colSpan={3} className="text-right font-semibold">
                    Total
                  </Td>
                  <Td className="text-right text-lg font-semibold">
                    {formatMoney(cart.total_minor, cart.currency)}
                  </Td>
                </tr>
              </tbody>
            </Table>
          </TableWrap>
          <p className="text-xs text-dim">
            Prices are the seeded catalog&apos;s. Whatever the agent said is ignored.
          </p>
        </section>

        <section aria-labelledby="checks-h" className="flex flex-col gap-2">
          <h2 id="checks-h" className="border-t-4 border-fg pt-3 text-xl font-semibold">
            Rules decided
          </h2>
          <ul>
            {cart.checks.map((c) => (
              <CheckRow key={`${c.name}:${c.reason_code ?? ""}`} check={c} />
            ))}
          </ul>
        </section>

        {cart.intent_fit && (
          <Notice tone="info" title="Advisory · AI">
            <p>
              Draft opinion: {cart.intent_fit.verdict.replace(/_/g, " ").toLowerCase()}
              {cart.intent_fit.reason_code ? ` (${cart.intent_fit.reason_code})` : ""}. It cannot
              block and cannot approve. The rules above already decided.
            </p>
          </Notice>
        )}
      </div>

      <aside className="flex min-w-0 flex-col gap-4 lg:sticky lg:top-6 lg:self-start">
        <Slab raised notched className="flex flex-col gap-4">
          <p className="text-xs font-bold uppercase tracking-[0.14em] text-flare">
            {blocked ? "Blocked" : "Decision needed"}
          </p>
          <h2 className="text-2xl font-semibold leading-tight">
            {blocked
              ? "This cart cannot go ahead."
              : `Approve ${formatMoney(cart.total_minor, cart.currency)} at ${merchants.join(", ")}?`}
          </h2>

          {mandate.data && (
            <div>
              <p className="tabular text-xs font-bold uppercase tracking-[0.14em] text-dim">
                Cap · {formatMoney(mandate.data.max_total_minor, mandate.data.currency)}
              </p>
              <Meter
                className="mt-2"
                part={mandate.data.spent_minor}
                whole={mandate.data.max_total_minor}
                extra={cart.total_minor}
                label="Cap used so far, with this cart shown in the warning colour"
              />
              <p className="tabular mt-2 flex flex-wrap gap-x-4 text-xs text-mute">
                <span>Spent {formatMoney(mandate.data.spent_minor, mandate.data.currency)}</span>
                <span>This cart {formatMoney(cart.total_minor, cart.currency)}</span>
                <span className="font-semibold text-fg">
                  Left now {formatMoney(mandate.data.remaining_minor, mandate.data.currency)}
                </span>
              </p>
            </div>
          )}

          <dl className="tabular border-t border-line text-sm">
            <div className="flex justify-between gap-3 border-b border-line py-2">
              <dt className="text-dim">Proposal hash</dt>
              <dd className="font-mono">
                {cart.proposal_hash.length > 12
                  ? `${cart.proposal_hash.slice(0, 6)}…${cart.proposal_hash.slice(-4)}`
                  : cart.proposal_hash}
              </dd>
            </div>
          </dl>

          {blocked && blockers.length > 0 && (
            <Notice tone="warn" title="Blocked by">
              <ul className="list-disc pl-5">
                {blockers.map((b) => (
                  <li key={`${b.name}:${b.reason_code}`}>
                    {reasonLabel(b.reason_code) ?? checkLabel(b.name)}
                  </li>
                ))}
              </ul>
            </Notice>
          )}

          {needsConfirm && !blocked && (
            <label className="flex cursor-pointer items-start gap-3 border-2 border-flare p-3 text-sm">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
                className="mt-0.5 h-5 w-5 accent-[var(--flare)]"
              />
              I read this and still want the cart
            </label>
          )}

          {moneyOff && (
            <Notice tone="warn" title="Money actions are switched off">
              Payments are paused on this deployment. You can still review the cart.
            </Notice>
          )}

          <p className="text-xs text-dim">
            Approve creates the PayPal order and sends you to PayPal to pay. Sandbox: test funds
            only.
          </p>
        </Slab>
        <ActionBar>
          {busy ? (
            <AgentWorking
              seconds={seconds}
              label={
                checking
                  ? "Checking whether your order was created. Do not pay twice."
                  : "Creating the sandbox PayPal order."
              }
            />
          ) : (
            <>
              <Button
                size="lg"
                disabled={!canApprove}
                className={canApprove ? "bg-flare text-bg hover:bg-flare" : undefined}
                onClick={() => void approve()}
              >
                Approve cart
              </Button>
              <Button asChild variant="secondary">
                <Link href="/intent">Reject</Link>
              </Button>
            </>
          )}
        </ActionBar>

        {blockedLink && (
          <Notice tone="warn" title="Payment link not opened">
            The link did not point to the PayPal sandbox, so it was not opened. Nothing was paid.
          </Notice>
        )}
        {failure !== null && <ApiErrorNotice error={failure} />}
      </aside>
    </div>
  );
}

export function CartView() {
  const { id } = useParams<{ id: string }>();
  const [entry, setEntry] = React.useState<CartEntry | null | undefined>(undefined);
  React.useEffect(() => setEntry(loadCart(id)), [id]);

  if (entry === undefined) return <Skeleton className="h-72 w-full" />;
  if (entry === null) {
    return (
      <Notice tone="warn" title="This cart is no longer here">
        <p>Carts live only for this browser tab. Ask the agent again to rebuild it.</p>
        <Button asChild className="mt-3" size="sm">
          <Link href="/intent">State what you need</Link>
        </Button>
      </Notice>
    );
  }
  return <CartBody entry={entry} />;
}
