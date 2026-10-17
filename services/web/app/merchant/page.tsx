import { MerchantDesk } from "@/components/merchant/merchant-desk";

export const metadata = { title: "Merchant · SafePayAI (sandbox demo)" };

export default function MerchantPage() {
  return (
    <div>
      <div className="pb-10 pt-10 md:pt-12">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-seal">/merchant</p>
        <h1 className="mt-3 font-display text-5xl font-black leading-[0.92] tracking-tight md:text-7xl">
          Your queue.
          <br />
          <span className="italic text-seal">Your shipments.</span>
        </h1>
      </div>
      <MerchantDesk />
    </div>
  );
}
