import { ReviewQueue } from "@/components/review/review-queue";

export const metadata = { title: "Review · SafePayAI (sandbox demo)" };

export default function ReviewPage() {
  return (
    <div>
      <div className="pb-10 pt-10 md:pt-12">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-seal">/review</p>
        <h1 className="mt-3 font-display text-5xl font-black leading-[0.92] tracking-tight md:text-7xl">
          Review queue.
          <br />
          <span className="italic text-seal">A person decides.</span>
        </h1>
      </div>
      <ReviewQueue />
    </div>
  );
}
