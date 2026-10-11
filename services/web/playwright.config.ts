import { defineConfig, devices } from "@playwright/test";

// Playwright e2e config. Wave 4 skeleton: a single smoke test (landing
// renders, SANDBOX banner present) stands in for the full E2E-* suite in
// test-plan.md. Real suite (cold-start, return-code matrix, a11y via axe,
// `@paypal-live` tag for the real-click sandbox flow) lands in later waves.
//
// webServer auto-starts `pnpm dev` against a local build for CI; point
// PLAYWRIGHT_BASE_URL at the hosted alias to run against staging instead.

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command: "pnpm build && pnpm start",
        url: "http://localhost:3000",
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
