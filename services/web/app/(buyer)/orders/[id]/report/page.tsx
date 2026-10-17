import { OrderReport } from "@/components/orders/order-report";

export const metadata = { title: "Report a problem · SafePayAI (sandbox demo)" };

export default function ReportPage() {
  return (
    <div className="pb-12">
      <div className="pb-10 pt-10 md:pt-12">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-seal">
          /orders/report
        </p>
        <h1 className="mt-3 font-display text-5xl font-black leading-[0.92] tracking-tight md:text-7xl">
          Report a problem.
          <br />
          <span className="italic text-seal">Say it plainly.</span>
        </h1>
      </div>
      <OrderReport />
    </div>
  );
}
