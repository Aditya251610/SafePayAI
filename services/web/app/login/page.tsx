import { Suspense } from "react";
import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { Tag } from "@/components/ui/tag";
import { LoginPanels } from "@/components/login/login-panels";

export const metadata = { title: "Sign in · SafePayAI (sandbox demo)" };

export default function LoginPage() {
  return (
    <div className="mx-auto max-w-page px-4 py-10 md:px-10">
      <header className="flex items-center justify-between border-b-2 border-line pb-6">
        <Link href="/" aria-label="SafePayAI home">
          <Logo />
        </Link>
        <Tag tone="dashed">Sandbox · test funds</Tag>
      </header>
      <div className="py-12">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-seal">/login</p>
        <h1 className="mt-3 font-display text-5xl font-black leading-[0.95] md:text-7xl">
          Sign in.
          <br />
          <span className="italic text-seal">Or try it.</span>
        </h1>
      </div>
      <Suspense fallback={null}>
        <LoginPanels />
      </Suspense>
    </div>
  );
}
