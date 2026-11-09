"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { IntentForm } from "@/components/intent/intent-form";
import { FlowRail } from "@/components/ui/rail";

export function IntentPage() {
  const mode = useSearchParams().get("mode") === "form" ? "form" : "intent";
  return (
    <div className="pb-12">
      <div className="flex flex-wrap items-end justify-between gap-8 pb-10 pt-10 md:pt-12">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-seal">/intent</p>
          <h1 className="mt-3 font-display text-5xl font-black leading-[0.92] tracking-tight md:text-7xl">
            State what you need.
            <br />
            <span className="italic text-seal">Get a cart.</span>
          </h1>
        </div>
        <FlowRail step={0} className="w-full max-w-[220px]" />
      </div>
      <p className="-mt-4 pb-6 text-sm text-mute">
        Prefer to pick items yourself?{" "}
        <Link href="/shop" className="font-semibold text-seal underline-offset-4 hover:underline">
          Browse the marketplace
        </Link>
        .
      </p>
      <IntentForm initialMode={mode} />
    </div>
  );
}
