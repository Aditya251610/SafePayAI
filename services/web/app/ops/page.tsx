import { OpsConsole } from "@/components/ops/ops-console";

export const metadata = { title: "Ops · SafePayAI (sandbox demo)" };

export default function OpsPage() {
  return (
    <div>
      <div className="pb-10 pt-10 md:pt-12">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-seal">/ops</p>
        <h1 className="mt-3 font-display text-5xl font-black leading-[0.92] tracking-tight md:text-7xl">
          Controls.
          <br />
          <span className="italic text-seal">One switch.</span>
        </h1>
      </div>
      <OpsConsole />
    </div>
  );
}
