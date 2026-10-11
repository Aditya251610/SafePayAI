import type { Metadata } from "next";

import "./globals.css";
import { ThemeProvider } from "@/components/shared/theme-provider";
import { SandboxBanner } from "@/components/shared/sandbox-banner";
import { FooterDisclosure } from "@/components/shared/footer-disclosure";
import { ThemeToggle } from "@/components/shared/theme-toggle";

export const metadata: Metadata = {
  title: "SafePayAI (sandbox demo)",
  description:
    "Buyer-signed purchase protection demo. Sandbox only, no real money, seeded catalog, simulated carrier.",
};

/**
 * Root layout - wraps every route, including (buyer)/(merchant) groups and
 * the public landing/about pages. Hosts the two REQ-WB-002/004-mandated,
 * non-dismissible disclosures (SandboxBanner, FooterDisclosure) so no screen
 * can ship without them, and the theme provider/toggle (REQ-WB-007).
 *
 * No SSR of authenticated data happens here or anywhere (prd.md sec 4
 * non-goal) - this shell is static; per-route client components fetch their
 * own session-gated data in Wave 5.
 */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="flex min-h-screen flex-col">
        <ThemeProvider>
          <SandboxBanner />
          <div className="flex justify-end px-4 py-2">
            <ThemeToggle />
          </div>
          <main className="flex-1">{children}</main>
          <FooterDisclosure />
        </ThemeProvider>
      </body>
    </html>
  );
}
