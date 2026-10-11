import { test, expect } from "@playwright/test";

// Smoke e2e test. Stands in for E2E-01 (full golden path) and the honesty
// crawl (E2E-V02) until Wave 5 builds those out against real BFF responses.

test("landing page loads and shows the persistent SANDBOX banner", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/Sandbox only\. No real money\./i)).toBeVisible();
  await expect(
    page.getByText(/Not affiliated with or endorsed by PayPal\./i),
  ).toBeVisible();
});

test("persona picker exposes buyer, merchant, and judge quick-path entries", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: /buyer/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /merchant/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /judge/i })).toBeVisible();
});
