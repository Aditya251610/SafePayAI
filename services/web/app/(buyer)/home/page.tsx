"use client";

import Link from "next/link";

import { MandateCard } from "@/components/domain/mandate-card";
import { ApiErrorNotice } from "@/components/shared/api-error";
import { WakingUp } from "@/components/shared/waking-up";
import { Button } from "@/components/ui/button";
import { CaseRail } from "@/components/ui/case-rail";
import { Skeleton } from "@/components/ui/skeleton";
import { Slab } from "@/components/ui/slab";
import { Tag } from "@/components/ui/tag";
import { ApiError } from "@/lib/api/errors";
import { formatDate } from "@/lib/format/date";
import { caseKindLabel, caseStateLabel, orderStatusLabel, shortId } from "@/lib/format/label";
import { formatMoney } from "@/lib/format/money";
import { useBuyerHome } from "@/lib/hooks/queries";

export default function HomePage() {
  const home = useBuyerHome();

  return (
    <div className="pb-12">
      <div className="flex flex-wrap items-end justify-between gap-6 pb-8 pt-10 md:pt-12">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-seal">/home</p>
          <h1 className="mt-3 font-display text-5xl font-black leading-[0.92] tracking-tight md:text-7xl">
            Your cap.
            <br />
            <span className="italic text-seal">Your orders.</span>
          </h1>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button asChild size="lg">
            <Link href="/intent">State what you need</Link>
          </Button>
          <Button asChild size="lg" variant="secondary">
            <Link href="/mandate/new">New mandate</Link>
          </Button>
        </div>
      </div>

      {home.isError ? (
        home.error instanceof ApiError && home.error.code === "UPSTREAM_WAKING" ? (
          <WakingUp />
        ) : (
          <ApiErrorNotice error={home.error} onRetry={() => void home.refetch()} />
        )
      ) : (
        <div className="flex flex-col gap-8 lg:flex-row lg:items-start">
          <section className="flex min-w-0 flex-[2] flex-col gap-4" aria-labelledby="mandates-h">
            <h2 id="mandates-h" className="border-t-4 border-fg pt-3 text-xl font-semibold">
              Mandates
            </h2>
            {home.isPending ? (
              <>
                <Skeleton className="h-44 w-full" />
                <Skeleton className="h-44 w-full" />
              </>
            ) : home.data.mandates.length === 0 ? (
              <Slab className="flex flex-col items-start gap-3">
                <p className="font-semibold">No mandate yet.</p>
                <p className="text-sm text-mute">
                  Sign a mandate to set the cap, the shops and the end date. The agent can do
                  nothing without one.
                </p>
                <Button asChild>
                  <Link href="/mandate/new">Sign your first mandate</Link>
                </Button>
              </Slab>
            ) : (
              home.data.mandates.map((m) => <MandateCard key={m.mandate_id} mandate={m} />)
            )}
          </section>

          <div className="flex min-w-0 flex-1 flex-col gap-8">
            <section className="flex flex-col gap-4" aria-labelledby="order-h">
              <h2 id="order-h" className="border-t-4 border-fg pt-3 text-xl font-semibold">
                Latest order
              </h2>
              {home.isPending ? (
                <Skeleton className="h-32 w-full" />
              ) : home.data.latest_order ? (
                <Slab className="flex flex-col gap-3">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="font-mono text-sm">
                      ORD-{shortId(home.data.latest_order.order_id, 6)}
                    </span>
                    <span className="tabular text-2xl font-semibold">
                      {formatMoney(
                        home.data.latest_order.total_minor,
                        home.data.latest_order.currency,
                      )}
                    </span>
                  </div>
                  <p className="text-sm text-mute">
                    {(home.data.latest_order.item_titles ?? []).join(", ") || "Order"} ·{" "}
                    {formatDate(home.data.latest_order.created_at)}
                  </p>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Tag tone={home.data.latest_order.status === "CAPTURED" ? "ret" : "neutral"}>
                      {orderStatusLabel(home.data.latest_order.status)}
                    </Tag>
                    <Link
                      href={`/orders/${home.data.latest_order.order_id}`}
                      className="text-sm font-semibold text-seal underline-offset-4 hover:underline"
                    >
                      View order →
                    </Link>
                  </div>
                </Slab>
              ) : (
                <Slab>
                  <p className="text-sm text-mute">No orders yet.</p>
                </Slab>
              )}
            </section>

            <section className="flex flex-col gap-4" aria-labelledby="case-h">
              <h2 id="case-h" className="border-t-4 border-fg pt-3 text-xl font-semibold">
                Active case
              </h2>
              {home.isPending ? (
                <Skeleton className="h-32 w-full" />
              ) : home.data.active_case ? (
                <Slab raised className="flex flex-col gap-3">
                  <div className="flex items-center justify-between gap-2">
                    <Tag tone="flare">{caseStateLabel(home.data.active_case.state)}</Tag>
                    <Tag>{caseKindLabel(home.data.active_case.kind)}</Tag>
                  </div>
                  <CaseRail state={home.data.active_case.state} />
                  <Link
                    href={`/cases/${home.data.active_case.case_id}`}
                    className="text-sm font-semibold text-seal underline-offset-4 hover:underline"
                  >
                    Open case →
                  </Link>
                </Slab>
              ) : (
                <Slab>
                  <p className="text-sm text-mute">No open case.</p>
                </Slab>
              )}
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
