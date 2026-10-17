import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";

/** Placeholder entry until the landing story ships. */
export default function HomePage() {
  return (
    <div className="mx-auto flex max-w-page flex-col gap-8 px-4 py-16 md:px-10">
      <Logo size={36} />
      <h1 className="font-display text-5xl font-black leading-[0.95] md:text-7xl">
        Your cap.
        <br />
        <span className="italic text-seal">Your rules.</span>
      </h1>
      <div>
        <Button asChild size="lg">
          <Link href="/login">Sign in</Link>
        </Button>
      </div>
    </div>
  );
}
