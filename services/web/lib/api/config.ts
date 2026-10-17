/**
 * The one base URL for every API call. The browser only ever talks to the
 * api-gateway through the same-origin `/api` rewrite, so the session cookie
 * stays first-party (contracts/frontend-integration-contract.md section 1).
 * Endpoint modules pass paths relative to this value and never build URLs
 * from anything else.
 */
export const API_BASE_URL: string = (process.env.NEXT_PUBLIC_PS_WEB_API_BASE ?? "/api").replace(
  /\/+$/,
  "",
);
