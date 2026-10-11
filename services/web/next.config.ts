import type { NextConfig } from "next";

// services/web/next.config.ts
//
// Wave 4 skeleton. Real values (rewrite target, security headers tuning) land
// in Wave 5 once PS_WEB_GATEWAY_INTERNAL_URL is live (deployment.md sec 1/4).
//
// Why a rewrite, not a redirect: the gateway cookie must look same-origin to
// the browser (SameSite=Lax survives only if the browser always sees the
// Vercel origin), per auth-gateway.md sec 2.3 and prd.md REQ-WB-001/R2.

const PS_WEB_GATEWAY_INTERNAL_URL = process.env.PS_WEB_GATEWAY_INTERNAL_URL;

const nextConfig: NextConfig = {
  reactStrictMode: true,

  async rewrites() {
    // TODO Wave 5: point this at the real Render gateway once
    // PS_WEB_GATEWAY_INTERNAL_URL is set in Vercel's server-side env.
    // Until then this is a no-op (falls through to Next's own handler, i.e.
    // nothing — there are no app/api routes in this skeleton yet).
    if (!PS_WEB_GATEWAY_INTERNAL_URL) {
      return [];
    }
    return [
      {
        source: "/api/:path*",
        destination: `${PS_WEB_GATEWAY_INTERNAL_URL}/:path*`,
      },
    ];
  },

  async headers() {
    // Security headers per deployment.md sec 4: no-referrer (PayPal `token`
    // query param must not leak via Referer), no inline script CSP, no
    // framing. Kept minimal for Wave 4; revisit CSP script-src hashing once
    // real third-party script needs (if any) are known.
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};

export default nextConfig;
