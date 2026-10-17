import { Suspense } from "react";

import { ReturnView } from "@/components/checkout/return-view";

export const metadata = { title: "Payment · SafePayAI (sandbox demo)" };

export default function Page() {
  return (
    <div className="pb-12">
      <div className="pb-10 pt-10 md:pt-12">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-seal">
          /checkout/return
        </p>
        <h1 className="mt-3 font-display text-5xl font-black leading-[0.92] tracking-tight md:text-7xl">
          Back from PayPal.
          <br />
          <span className="italic text-seal">Server decides.</span>
        </h1>
      </div>
      <Suspense fallback={null}>
        <ReturnView />
      </Suspense>
    </div>
  );
}
