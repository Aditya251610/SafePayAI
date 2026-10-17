import { Suspense } from "react";

import { CancelView } from "@/components/checkout/return-view";

export const metadata = { title: "Payment · SafePayAI (sandbox demo)" };

export default function Page() {
  return (
    <div className="pb-12">
      <div className="pb-10 pt-10 md:pt-12">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-seal">
          /checkout/cancel
        </p>
        <h1 className="mt-3 font-display text-5xl font-black leading-[0.92] tracking-tight md:text-7xl">
          You left
          <br />
          <span className="italic text-seal">PayPal.</span>
        </h1>
      </div>
      <Suspense fallback={null}>
        <CancelView />
      </Suspense>
    </div>
  );
}
