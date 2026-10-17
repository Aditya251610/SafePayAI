import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi } from "./mock-api";
import { buyerRoutes } from "./routes";
import { IDS } from "../mocks/fixtures";
import { BANNED_PHRASES } from "../../lib/honesty/banned";

test("a merchant sees the queue and opens a case", async ({ page }) => {
  await mockApi(page, { role: "merchant", routes: buyerRoutes() });
  await page.goto("/merchant");
  await expect(page.getByText("2 shipments in motion")).toBeVisible();
  await page.getByRole("link", { name: "Open" }).first().click();
  await expect(page).toHaveURL(new RegExp(`/merchant/cases/${IDS.case}$`));
  await expect(page.getByText("No amount field.")).toBeVisible();
});

test("overriding an offer needs a confirmation", async ({ page }) => {
  const m = await mockApi(page, { role: "merchant", routes: buyerRoutes() });
  await page.goto(`/merchant/cases/${IDS.case}`);
  await page.getByRole("button", { name: "Override the offer" }).click();
  expect(m.calls).not.toContain(`POST /resolution/cases/${IDS.case}/merchant-action`);
  await page.getByRole("button", { name: "Yes, continue" }).click();
  await expect(page.getByText("Done")).toBeVisible();
});

test("marking an order shipped labels the carrier simulated", async ({ page }) => {
  await mockApi(page, { role: "merchant", routes: buyerRoutes() });
  await page.goto("/merchant");
  await page.getByLabel("Order id").fill(IDS.order);
  await page.getByLabel("Tracking number").fill("TRK-1");
  await page.getByLabel("Carrier name").fill("SimPost");
  await page.getByRole("button", { name: "Mark shipped" }).click();
  await expect(page.getByText("Marked shipped")).toBeVisible();
  await expect(page.getByText(/SIMULATED CARRIER/)).toBeVisible();
});

test("a buyer on a staff page sees the wrong-account message", async ({ page }) => {
  await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  await page.goto("/merchant");
  await expect(page.getByText("Wrong account type")).toBeVisible();
});

test("phone width shows the larger-screen note and the page does not scroll sideways", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page, { role: "merchant", routes: buyerRoutes() });
  await page.goto("/merchant");
  await expect(page.getByText("Use a larger screen")).toBeVisible();
  await expect(page.getByText("Case queue")).toBeHidden();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});

for (const scheme of ["dark", "light"] as const) {
  test(`merchant screens are accessible with no banned claims (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await mockApi(page, { role: "merchant", routes: buyerRoutes() });
    for (const [path, ready] of [
      ["/merchant", "Case queue"],
      [`/merchant/cases/${IDS.case}`, "No amount field."],
    ] as const) {
      await page.goto(path);
      await page.getByText(ready).first().waitFor();
      const r = await new AxeBuilder({ page }).analyze();
      expect(r.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual(
        [],
      );
      const text = (await page.locator("body").innerText()).toLowerCase();
      expect(BANNED_PHRASES.filter((p) => text.includes(p))).toEqual([]);
    }
  });
}
