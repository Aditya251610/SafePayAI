import type { Metadata } from "next";
import { Bodoni_Moda, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";

import "./globals.css";
import { Providers } from "./providers";
import { SandboxBanner } from "@/components/shared/sandbox-banner";
import { FooterDisclosure } from "@/components/shared/footer-disclosure";

const display = Bodoni_Moda({
  subsets: ["latin"],
  weight: ["700", "800", "900"],
  style: ["normal", "italic"],
  variable: "--font-display",
  display: "swap",
});
const sans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});
const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "SafePayAI (sandbox demo)",
  description:
    "Buyer-signed purchase protection demo. Sandbox only, no real money, seeded catalog, simulated carrier.",
};

/** Root frame. The sandbox banner and footer disclosure cannot be skipped by any route. */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${display.variable} ${sans.variable} ${mono.variable}`}
    >
      <body className="flex min-h-screen flex-col">
        <Providers>
          <SandboxBanner />
          <main className="flex-1">{children}</main>
          <FooterDisclosure />
        </Providers>
      </body>
    </html>
  );
}
