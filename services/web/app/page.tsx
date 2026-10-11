import Link from "next/link";

import { AceternityHero } from "@/components/landing/aceternity-hero";
import WebglCanvas from "@/components/landing/webgl-canvas-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

// Client-only, ssr:false per tech-stack.md T3 (WebGL/canvas hydration risk) -
// the ssr:false dynamic import itself lives in webgl-canvas-client.tsx (a
// Client Component boundary) so this page can stay a Server Component. This
// is the ONLY route allowed to import WebGL/Aceternity-class components
// (spec.md sec 10 WHERE rule, tech-stack.md T2 bundle-size mitigation) - no
// money-path route may import this module.

/**
 * Landing / persona picker (REQ-WB-010). Judge quick path per prd.md
 * persona J / sprint-tasks.md WEB-S4-08. Session creation (buyer ephemeral,
 * merchant shared login) is NOT wired yet - TODO Wave 5, see
 * lib/api-client.ts. Links below point at the real buyer/merchant entry
 * routes so the IA is navigable even before session logic exists.
 */
export default function LandingPage() {
  return (
    <div className="relative isolate overflow-hidden">
      <div className="absolute inset-0 -z-10">
        <WebglCanvas />
      </div>

      <section className="flex min-h-[70vh] flex-col items-center justify-center gap-10 px-4 py-20">
        <AceternityHero
          title="SafePayAI"
          subtitle="Buyer-signed purchase protection for agentic shopping. Sandbox demo - no real money."
        />

        <div className="grid w-full max-w-3xl gap-4 sm:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle>Buyer</CardTitle>
              <CardDescription>Start an ephemeral demo session</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild className="w-full">
                <Link href="/start">Buyer</Link>
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Merchant</CardTitle>
              <CardDescription>Shared demo login (disclosed)</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="secondary" className="w-full">
                <Link href="/orders">Merchant</Link>
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Judge quick path</CardTitle>
              <CardDescription>4 numbered steps, no signup</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline" className="w-full">
                <Link href="/about">Judge quick path</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </section>
    </div>
  );
}
