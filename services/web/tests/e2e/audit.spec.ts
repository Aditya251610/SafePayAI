import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi } from "./mock-api";
import { buyerRoutes } from "./routes";
import { BANNED_PHRASES } from "../../lib/honesty/banned";

for (const role of ["buyer", "merchant", "operator", "reviewer"] as const) {
  test(`${role} can open the audit log`, async ({ page }) => {
    await mockApi(page, { role, routes: buyerRoutes() });
    await page.goto("/audit");
    await expect(page.getByText("Chain intact")).toBeVisible();
    await expect(page.getByText("Mandate Signed").filter({ visible: true }).first()).toBeVisible();
  });
}

test("a signed-out visitor is sent to login", async ({ page }) => {
  await mockApi(page, { role: null, routes: buyerRoutes() });
  await page.goto("/audit");
  await expect(page).toHaveURL(/\/login\?next=%2Faudit/);
});

test("phone width shows entries as cards without sideways scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  await page.goto("/audit");
  await page.getByText("Mandate Signed").filter({ visible: true }).first().waitFor();
  await expect(page.getByRole("table")).toBeHidden();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});

for (const scheme of ["dark", "light"] as const) {
  test(`audit log is accessible with no banned claims (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await mockApi(page, { role: "buyer", routes: buyerRoutes() });
    await page.goto("/audit");
    await page.getByText("Mandate Signed").filter({ visible: true }).first().waitFor();
    const r = await new AxeBuilder({ page }).analyze();
    expect(r.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual(
      [],
    );
    const text = (await page.locator("body").innerText()).toLowerCase();
    expect(BANNED_PHRASES.filter((p) => text.includes(p))).toEqual([]);
  });
}
