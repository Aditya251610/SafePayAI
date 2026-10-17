import type { NextConfig } from "next";

// The browser only ever talks to /api on its own origin. This rewrite forwards
// those calls to the gateway so the __Host- session cookie stays first-party
// and SameSite=Lax keeps working. The target is server-side only.
const GATEWAY_INTERNAL_URL = process.env.PS_WEB_GATEWAY_INTERNAL_URL;

const nextConfig: NextConfig = {
  reactStrictMode: true,

  async rewrites() {
    if (!GATEWAY_INTERNAL_URL) return [];
    return [{ source: "/api/:path*", destination: `${GATEWAY_INTERNAL_URL}/:path*` }];
  },

  async headers() {
    // no-referrer keeps PayPal's return token out of any Referer header.
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), payment=()",
          },
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
