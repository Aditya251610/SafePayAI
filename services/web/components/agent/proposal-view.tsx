"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { AgentWorking, useElapsed } from "@/components/agent/agent-working";
import { ApiErrorNotice } from "@/components/shared/api-error";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { Slab } from "@/components/ui/slab";
import { Tag } from "@/components/ui/tag";
import { api } from "@/lib/api";
import { newIdempotencyKey } from "@/lib/api/ids";
import { loadProposal, saveCart, type ProposalEntry } from "@/lib/storage/entries";

const CANNOT = [
  "Approve a cart or spend a dollar",
  "Raise the cap or the per-cart max",
  "Add a shop to the allowlist",
  "Open, change or send a refund",
];

function Boundary() {
  return (
    <Slab className="flex flex-col gap-3">
      <p className="text-xs font-bold uppercase tracking-[0.16em] text-dim">The agent cannot</p>
      <ul className="text-sm text-mute">
        {CANNOT.map((c) => (
          <li key={c} className="flex gap-3 border-b border-line py-2">
            <span className="font-bold text-flare">No</span>
            {c}
          </li>
        ))}
      </ul>
      <p className="text-xs text-dim">The AI classifies and drafts. It never decides money.</p>
    </Slab>
  );
}

/** What the agent proposed. The cart is only built, and checked by rules, when the buyer asks. */
export function ProposalView() {
  const { proposal_id: proposalId } = useParams<{ proposal_id: string }>();
  const router = useRouter();
  const [entry, setEntry] = React.useState<ProposalEntry | null | undefined>(undefined);
  const [building, setBuilding] = React.useState(false);
  const [failure, setFailure] = React.useState<unknown>(null);
  const key = React.useRef<string | null>(null);
  const seconds = useElapsed(building);

  React.useEffect(() => {
    setEntry(loadProposal(decodeURIComponent(proposalId)));
  }, [proposalId]);

  async function buildCart() {
    if (!entry) return;
    setFailure(null);
    setBuilding(true);
    key.current ??= newIdempotencyKey();
    try {
      const cart = await api.checkout.createCart(
        {
          mandate_id: entry.mandateId,
          proposal_id: entry.proposal.proposal_id,
          lines: entry.proposal.lines.map((l) => ({ sku: l.sku, qty: l.quantity })),
        },
        { idempotencyKey: key.current },
      );
      saveCart({ cart, mandateId: entry.mandateId });
      router.push(`/cart/${cart.cart_id}`);
    } catch (e) {
      setFailure(e);
      setBuilding(false);
    }
  }

  if (entry === undefined) return <Skeleton className="h-56 w-full" />;

  if (entry === null) {
    return (
      <Notice tone="warn" title="This proposal is no longer here">
        <p>Proposals live only for this browser tab. Ask the agent again.</p>
        <Button asChild className="mt-3" size="sm">
          <Link href="/intent">State what you need</Link>
        </Button>
      </Notice>
    );
  }

  const p = entry.proposal;

  if (p.status !== "OK") {
    const copy: Record<string, { title: string; text: string }> = {
      NO_MATCH: {
        title: "Nothing matched",
        text: p.no_match_reason ?? "Nothing in the seeded catalog fits this inside your mandate.",
      },
      NO_PROPOSAL: {
        title: "The agent could not build a cart",
        text: "Try different words, or use the form instead.",
      },
      AI_PAUSED: {
        title: "The AI helper is paused",
        text: "You can still ask with the form. It does not use the AI.",
      },
    };
    const c = copy[p.status] ?? { title: "No cart this time", text: "Try again or use the form." };
    return (
      <div className="flex max-w-2xl flex-col gap-4">
        <Notice tone="warn" title={c.title}>
          {c.text}
        </Notice>
        <div className="flex flex-wrap gap-3">
          <Button asChild>
            <Link href="/intent">Try different words</Link>
          </Button>
          <Button asChild variant="secondary">
            <Link href="/intent?mode=form">Use the form</Link>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="flex min-w-0 flex-col gap-6">
        <Slab raised notched className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <Tag tone="seal">Draft · decides nothing</Tag>
            {p.source === "cached" && <Tag tone="dashed">Cached answer</Tag>}
            {p.source === "form" && <Tag tone="dashed">From the form</Tag>}
          </div>
          <h2 className="font-display text-3xl font-extrabold">The agent suggests</h2>
          <ul className="tabular border-t border-line">
            {p.lines.map((l) => (
              <li key={l.sku} className="flex justify-between gap-4 border-b border-line py-3">
                <span>
                  {l.display_title ?? l.sku}
                  <span className="ml-2 font-mono text-xs text-dim">{l.sku}</span>
                </span>
                <span>× {l.quantity}</span>
              </li>
            ))}
          </ul>
          {p.rationale && (
            <p className="text-sm text-mute">
              <span className="font-bold uppercase tracking-[0.1em] text-dim">
                Draft reasoning ·{" "}
              </span>
              {p.rationale}
            </p>
          )}
          {typeof p.confidence === "number" && (
            <p className="text-xs text-dim">
              Draft confidence {Math.round(p.confidence * 100)}%. It may be wrong.
            </p>
          )}
          {building ? (
            <AgentWorking
              seconds={seconds}
              label="Checking the cart against your mandate. Rules decide each check."
              onRetry={() => void buildCart()}
            />
          ) : (
            <Button size="lg" className="self-start" onClick={() => void buildCart()}>
              Check against my mandate
            </Button>
          )}
          <p className="text-xs text-dim">
            Prices come from the seeded catalog, not from the agent. The next screen shows what the
            rules decided.
          </p>
        </Slab>
        {failure !== null && <ApiErrorNotice error={failure} onRetry={() => void buildCart()} />}
      </div>
      <Boundary />
    </div>
  );
}
