import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi } from "./mock-api";
import { buyerRoutes } from "./routes";
import { BANNED_PHRASES } from "../../lib/honesty/banned";

test("an operator unfreezes refunds after confirming", async ({ page }) => {
  const m = await mockApi(page, { role: "operator", routes: buyerRoutes() });
  await page.goto("/ops");
  await page.getByLabel("Reason").fill("Demo reset");
  await page.getByRole("button", { name: "Unfreeze refunds" }).click();
  expect(m.calls).not.toContain("POST /ops/freeze");
  await page.getByRole("button", { name: "Yes, unfreeze" }).click();
  await expect(page.getByText(/Refunds are unfrozen/)).toBeVisible();
});

test("the demo clock advances", async ({ page }) => {
  const m = await mockApi(page, { role: "operator", routes: buyerRoutes() });
  await page.goto("/ops");
  await page.getByRole("button", { name: "+1 day" }).click();
  await expect.poll(() => m.calls.includes("POST /tracking/demo/clock/advance")).toBe(true);
});

test("a reviewer sees the queue, read-only", async ({ page }) => {
  await mockApi(page, { role: "reviewer", routes: buyerRoutes() });
  await page.goto("/review");
  await expect(page.getByText("Read-only in this build")).toBeVisible();
  await expect(page.getByText("POLICY_CAP")).toBeVisible();
});

test("a merchant cannot open ops", async ({ page }) => {
  await mockApi(page, { role: "merchant", routes: buyerRoutes() });
  await page.goto("/ops");
  await expect(page.getByText("Wrong account type")).toBeVisible();
});

for (const scheme of ["dark", "light"] as const) {
  test(`ops and review are accessible with no banned claims (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    for (const [role, path, ready] of [
      ["operator", "/ops", "Refunds are paused."],
      ["reviewer", "/review", "Read-only in this build"],
    ] as const) {
      await mockApi(page, { role, routes: buyerRoutes() });
      await page.goto(path);
      await page.getByText(ready).first().waitFor();
      const r = await new AxeBuilder({ page }).analyze();
      expect(r.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual(
        [],
      );
      const text = (await page.locator("body").innerText()).toLowerCase();
      expect(BANNED_PHRASES.filter((p) => text.includes(p))).toEqual([]);
      await page.unroute("**/api/**");
    }
  });
}
