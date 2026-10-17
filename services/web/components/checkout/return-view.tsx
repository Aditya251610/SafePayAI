"use client";

import * as React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { AgentWorking, useElapsed } from "@/components/agent/agent-working";
import { ApiErrorNotice } from "@/components/shared/api-error";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { Slab } from "@/components/ui/slab";
import { Tag } from "@/components/ui/tag";
import { api } from "@/lib/api";
import { AmbiguousOutcomeError } from "@/lib/api/errors";
import { newIdempotencyKey } from "@/lib/api/ids";
import { pollUntil } from "@/lib/api/reconcile";
import { isFinalStatus, outcomeFor } from "@/lib/checkout/outcome";
import { orderStatusLabel } from "@/lib/format/label";
import { loadLastOrder } from "@/lib/storage/entries";

type Phase = "working" | "ready" | "none";

interface State {
  phase: Phase;
  orderId: string | null;
  status: string | null;
  messageCode: string | null;
  mandateId: string | null;
}

const PENDING = new Set(["CAPTURE_PENDING", "APPROVED", "CAPTURE_UNKNOWN", "AWAITING_APPROVAL"]);

/** Where PayPal sends the buyer back. The server's order record is the truth. */
export function ReturnView() {
  const params = useSearchParams();
  const [state, setState] = React.useState<State>({
    phase: "working",
    orderId: null,
    status: null,
    messageCode: null,
    mandateId: null,
  });
  const [failure, setFailure] = React.useState<unknown>(null);
  const [polling, setPolling] = React.useState(false);
  const [manual, setManual] = React.useState(false);
  const started = React.useRef(false);
  const captureKey = React.useRef<string | null>(null);
  const seconds = useElapsed(state.phase === "working" || polling);

  const apply = React.useCallback(
    (patch: Partial<State>) => setState((s) => ({ ...s, ...patch })),
    [],
  );

  const follow = React.useCallback(
    async (orderId: string) => {
      setPolling(true);
      try {
        const result = await pollUntil(
          async () => {
            const o = await api.checkout.order(orderId);
            apply({ status: o.status, mandateId: o.mandate_id });
            return o;
          },
          (o) => !PENDING.has(o.status) || isFinalStatus(o.status),
        );
        apply({ status: result.value.status, mandateId: result.value.mandate_id });
      } catch (e) {
        setFailure(e);
      } finally {
        setPolling(false);
      }
    },
    [apply],
  );

  React.useEffect(() => {
    if (started.current) return;
    started.current = true;

    const returnState = params.get("state");
    const token = params.get("token");
    const payerId = params.get("PayerID") ?? params.get("payer_id");
    const last = loadLastOrder();

    // The PayPal token must not stay in the address bar or history.
    if (returnState || token || payerId) window.history.replaceState(null, "", "/checkout/return");

    void (async () => {
      if (returnState && token && payerId) {
        try {
          const r = await api.checkout.completeReturn({
            state: returnState,
            token,
            payer_id: payerId,
          });
          apply({
            phase: "ready",
            orderId: r.order_id,
            status: r.status,
            messageCode: r.message_code ?? null,
            mandateId: last?.mandateId ?? null,
          });
          if (PENDING.has(r.status)) void follow(r.order_id);
        } catch (e) {
          if (e instanceof AmbiguousOutcomeError && last) {
            apply({
              phase: "ready",
              orderId: last.orderId,
              status: "CAPTURE_UNKNOWN",
              mandateId: last.mandateId ?? null,
            });
            void follow(last.orderId);
          } else {
            setFailure(e);
            apply({
              phase: last ? "ready" : "none",
              orderId: last?.orderId ?? null,
              mandateId: last?.mandateId ?? null,
            });
          }
        }
        return;
      }
      if (last) {
        apply({ phase: "ready", orderId: last.orderId, mandateId: last.mandateId ?? null });
        void follow(last.orderId);
        return;
      }
      apply({ phase: "none" });
    })();
  }, [params, apply, follow]);

  async function checkPayment() {
    if (!state.orderId) return;
    setFailure(null);
    setManual(true);
    captureKey.current ??= newIdempotencyKey();
    try {
      const o = await api.checkout.capture(state.orderId, { idempotencyKey: captureKey.current });
      apply({ status: o.status, mandateId: o.mandate_id });
    } catch (e) {
      if (e instanceof AmbiguousOutcomeError) void follow(state.orderId);
      else setFailure(e);
    } finally {
      setManual(false);
    }
  }

  if (state.phase === "working") {
    return (
      <AgentWorking
        seconds={seconds}
        label="Capturing your payment. Do not retry on a timer; the server is the record."
      />
    );
  }

  if (state.phase === "none" || !state.status) {
    return (
      <div className="flex max-w-xl flex-col gap-4">
        {failure !== null ? (
          <ApiErrorNotice error={failure} />
        ) : polling ? (
          <AgentWorking seconds={seconds} label="Reading your order." />
        ) : (
          <Notice tone="info" title="Nothing to finish here">
            This page completes a PayPal payment. Open your orders to see where things stand.
          </Notice>
        )}
        <Button asChild variant="secondary" className="self-start">
          <Link href="/orders">Your orders</Link>
        </Button>
      </div>
    );
  }

  const outcome = outcomeFor(state.status);
  const code = state.messageCode;
  const still = PENDING.has(state.status);

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <Slab raised notched className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Tag
            tone={
              outcome.tone === "ok"
                ? "solid-ret"
                : outcome.tone === "warn"
                  ? "solid-flare"
                  : outcome.tone === "pending"
                    ? "seal"
                    : "neutral"
            }
          >
            {orderStatusLabel(state.status)}
          </Tag>
          {code && <span className="font-mono text-xs text-dim">message_code · {code}</span>}
        </div>
        <h2 className="font-display text-4xl font-extrabold leading-tight">{outcome.title}</h2>
        <p className="text-mute">{outcome.text}</p>

        {polling && still && (
          <p role="status" className="tabular text-xs text-dim">
            Checking again… {seconds} s
          </p>
        )}

        <div className="flex flex-wrap gap-3 pt-2">
          {state.orderId && (
            <Button asChild size="lg">
              <Link href={`/orders/${state.orderId}`}>
                {state.status === "CAPTURED" ? "Track order" : "Open order"}
              </Link>
            </Button>
          )}
          {state.orderId && still && (
            <Button
              size="lg"
              variant="secondary"
              disabled={manual || polling}
              onClick={() => void checkPayment()}
            >
              {manual ? "Checking…" : "Check payment"}
            </Button>
          )}
          {outcome.action === "mandate" && state.mandateId && (
            <Button asChild variant="secondary" size="lg">
              <Link href={`/mandate/${state.mandateId}`}>View mandate</Link>
            </Button>
          )}
          {outcome.action === "orders" && (
            <Button asChild variant="secondary" size="lg">
              <Link href="/orders">Your orders</Link>
            </Button>
          )}
        </div>
        <p className="text-xs text-dim">
          Sandbox: test funds only. Refunds are merchant-funded via PayPal.
        </p>
      </Slab>
      {failure !== null && <ApiErrorNotice error={failure} />}
    </div>
  );
}

/** Where PayPal sends the buyer when they leave without paying. */
export function CancelView() {
  const params = useSearchParams();
  const started = React.useRef(false);
  const [done, setDone] = React.useState<{ orderId: string; status: string } | null>(null);
  const [failure, setFailure] = React.useState<unknown>(null);

  React.useEffect(() => {
    if (started.current) return;
    started.current = true;
    const s = params.get("state");
    window.history.replaceState(null, "", "/checkout/cancel");
    if (!s) {
      setFailure(null);
      return;
    }
    api.checkout
      .cancelReturn(s)
      .then((r) => setDone({ orderId: r.order_id, status: r.status }))
      .catch(setFailure);
  }, [params]);

  const outcome = outcomeFor(done?.status ?? "CANCELLED_BUYER");
  return (
    <div className="flex max-w-xl flex-col gap-4">
      {failure !== null ? (
        <ApiErrorNotice error={failure} />
      ) : (
        <Slab raised notched className="flex flex-col gap-3">
          <Tag tone="neutral" className="self-start">
            {orderStatusLabel(done?.status ?? "CANCELLED_BUYER")}
          </Tag>
          <h2 className="font-display text-4xl font-extrabold leading-tight">{outcome.title}</h2>
          <p className="text-mute">{outcome.text}</p>
        </Slab>
      )}
      <Button asChild variant="secondary" className="self-start">
        <Link href="/orders">Your orders</Link>
      </Button>
    </div>
  );
}
