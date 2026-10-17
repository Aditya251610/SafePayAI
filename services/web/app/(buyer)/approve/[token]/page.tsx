import { ApproveView } from "@/components/cases/approve-view";

export const metadata = { title: "Approve · SafePayAI (sandbox demo)", referrer: "no-referrer" };

export default function ApprovePage() {
  return (
    <div className="pb-12">
      <div className="pb-10 pt-10 md:pt-12">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-seal">/approve</p>
        <h1 className="mt-3 font-display text-5xl font-black leading-[0.92] tracking-tight md:text-7xl">
          Read it.
          <br />
          <span className="italic text-seal">Then approve.</span>
        </h1>
      </div>
      <ApproveView />
    </div>
  );
}
