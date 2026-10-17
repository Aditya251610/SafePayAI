import type { Metadata } from "next";
import localFont from "next/font/local";

import "./globals.css";
import { Providers } from "./providers";
import { SandboxBanner } from "@/components/shared/sandbox-banner";
import { FooterDisclosure } from "@/components/shared/footer-disclosure";

// Fonts ship with the app (latin subset) so a build never depends on a font CDN.
const display = localFont({
  src: [
    { path: "./fonts/bodoni-normal-700-900.woff2", weight: "700 900", style: "normal" },
    { path: "./fonts/bodoni-italic-700-900.woff2", weight: "700 900", style: "italic" },
  ],
  variable: "--font-display",
  display: "swap",
});
const sans = localFont({
  src: [{ path: "./fonts/plex-sans-variable.woff2", weight: "400 700", style: "normal" }],
  variable: "--font-sans",
  display: "swap",
});
const mono = localFont({
  src: [
    { path: "./fonts/plex-mono-normal-400.woff2", weight: "400", style: "normal" },
    { path: "./fonts/plex-mono-normal-500.woff2", weight: "500", style: "normal" },
  ],
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
