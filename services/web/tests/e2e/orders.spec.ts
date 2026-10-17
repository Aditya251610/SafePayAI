import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi } from "./mock-api";
import { buyerRoutes } from "./routes";
import { IDS } from "../mocks/fixtures";
import { BANNED_PHRASES } from "../../lib/honesty/banned";

test("orders list opens an order, whose receipt keeps every disclosure", async ({ page }) => {
  await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  await page.goto("/orders");
  await page.getByRole("link", { name: /ORD-/ }).first().click();
  await expect(page).toHaveURL(new RegExp(`/orders/${IDS.order}$`));
  await expect(page.getByText("Simulated carrier").first()).toBeVisible();
  await page.getByRole("tab", { name: "Receipt" }).click();
  await expect(page.getByText("Merchant-funded via PayPal refund")).toBeVisible();
  await expect(page.getByText("Sandbox only", { exact: true })).toBeVisible();
});

test("report a problem opens a case", async ({ page }) => {
  const m = await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  await page.goto(`/orders/${IDS.order}/report`);
  await page.getByLabel("What went wrong?").fill("It never arrived.");
  await page.getByRole("button", { name: "Open case" }).click();
  await expect(page).toHaveURL(new RegExp(`/cases/${IDS.case}$`));
  expect(m.calls).toContain("POST /resolution/cases/report");
});

test("phone width shows cards, desktop shows the table", async ({ page }) => {
  await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/orders");
  await expect(page.getByRole("table")).toBeHidden();
  await expect(page.getByRole("link", { name: /ORD-/ }).first()).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
  await page.setViewportSize({ width: 1280, height: 900 });
  await expect(page.getByRole("table")).toBeVisible();
});

for (const scheme of ["dark", "light"] as const) {
  test(`order screens are accessible with no banned claims (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await mockApi(page, { role: "buyer", routes: buyerRoutes() });
    for (const [path, ready] of [
      ["/orders", "newest first"],
      [`/orders/${IDS.order}`, "Audit chain"],
      [`/orders/${IDS.order}/report`, "AI reads. Rules decide."],
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
