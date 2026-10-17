import { ProposalView } from "@/components/agent/proposal-view";

export const metadata = { title: "Agent · SafePayAI (sandbox demo)" };

export default function AgentPage() {
  return (
    <div className="pb-12">
      <div className="pb-10 pt-10 md:pt-12">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-seal">/agent</p>
        <h1 className="mt-3 font-display text-5xl font-black leading-[0.92] tracking-tight md:text-7xl">
          The agent drafts.
          <br />
          <span className="italic text-seal">Rules decide.</span>
        </h1>
      </div>
      <ProposalView />
    </div>
  );
}
