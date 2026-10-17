import { MandateForm } from "@/components/mandate/mandate-form";

export const metadata = { title: "New mandate · SafePayAI (sandbox demo)" };

export default function MandateNewPage() {
  return (
    <div className="pb-12">
      <div className="pb-10 pt-10 md:pt-12">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-seal">/mandate/new</p>
        <h1 className="mt-3 font-display text-5xl font-black leading-[0.92] tracking-tight md:text-7xl">
          Set the cap.
          <br />
          <span className="italic text-seal">Sign once.</span>
        </h1>
        <p className="mt-4 max-w-xl text-mute">
          The mandate is the only authority the agent has. You read the exact text, then you sign
          that text.
        </p>
      </div>
      <MandateForm />
    </div>
  );
}
