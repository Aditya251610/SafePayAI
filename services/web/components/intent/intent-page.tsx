"use client";

import { useSearchParams } from "next/navigation";

import { IntentForm } from "@/components/intent/intent-form";

export function IntentPage() {
  const mode = useSearchParams().get("mode") === "form" ? "form" : "intent";
  return (
    <div className="pb-12">
      <div className="pb-10 pt-10 md:pt-12">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-seal">/intent</p>
        <h1 className="mt-3 font-display text-5xl font-black leading-[0.92] tracking-tight md:text-7xl">
          State what you need.
          <br />
          <span className="italic text-seal">Get a cart.</span>
        </h1>
      </div>
      <IntentForm initialMode={mode} />
    </div>
  );
}
