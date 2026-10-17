import { AuditLog } from "@/components/audit/audit-log";

export const metadata = { title: "Audit log · SafePayAI (sandbox demo)" };

export default function AuditPage() {
  return (
    <div>
      <div className="pb-10 pt-10 md:pt-12">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-seal">/audit</p>
        <h1 className="mt-3 font-display text-5xl font-black leading-[0.92] tracking-tight md:text-7xl">
          Every action.
          <br />
          <span className="italic text-seal">Chained.</span>
        </h1>
      </div>
      <AuditLog />
    </div>
  );
}
