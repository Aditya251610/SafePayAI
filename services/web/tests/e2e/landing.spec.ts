import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi } from "./mock-api";
import { BANNED_PHRASES } from "../../lib/honesty/banned";

for (const scheme of ["dark", "light"] as const) {
  test.describe(`${scheme} theme`, () => {
    test.use({ colorScheme: scheme });

    test("entry page shows the sandbox banner and footer disclosure", async ({ page }) => {
      await mockApi(page, null);
      await page.goto("/");
      await expect(page.getByText(/Sandbox only\. No real money\./i)).toBeVisible();
      await expect(page.getByText(/Not affiliated with or endorsed by PayPal\./i)).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("data-theme", scheme);
    });

    test("entry page has no serious accessibility violations", async ({ page }) => {
      await mockApi(page, null);
      await page.goto("/");
      const results = await new AxeBuilder({ page }).analyze();
      const serious = results.violations.filter(
        (v) => v.impact === "serious" || v.impact === "critical",
      );
      expect(serious).toEqual([]);
    });

    test("entry page text contains no banned claims", async ({ page }) => {
      await mockApi(page, null);
      await page.goto("/");
      const text = (await page.locator("body").innerText()).toLowerCase();
      expect(BANNED_PHRASES.filter((p) => text.includes(p))).toEqual([]);
    });
  });
}

test("unknown pages show the not-found message", async ({ page }) => {
  await mockApi(page, null);
  const res = await page.goto("/definitely-missing");
  expect(res?.status()).toBe(404);
  await expect(page.getByText("Page not found.")).toBeVisible();
});
