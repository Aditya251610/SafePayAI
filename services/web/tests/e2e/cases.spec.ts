import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi } from "./mock-api";
import { buyerRoutes } from "./routes";
import { IDS, offer } from "../mocks/fixtures";
import { BANNED_PHRASES } from "../../lib/honesty/banned";

async function seedReport(page: Page) {
  await page.addInitScript(
    ([key, value]) => window.sessionStorage.setItem(key as string, value as string),
    [
      `ps:report:${IDS.case}`,
      JSON.stringify({
        case_id: IDS.case,
        state: "OFFERED",
        kind: "LATE",
        origin: "BUYER_REPORT",
        reasons: [{ code: "IN_TERMS", text: "Order inside mandate" }],
        offer,
        protection: {},
      }),
    ],
  );
}

test("report then accept the offer", async ({ page }) => {
  await seedReport(page);
  const m = await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  await page.goto(`/cases/${IDS.case}`);
  await expect(page.getByRole("heading", { name: "Refund $48.20" })).toBeVisible();
  await page.getByRole("button", { name: "Accept offer" }).click();
  await expect(page.getByText("Refund in progress.")).toBeVisible();
  expect(m.calls).toContain(`POST /resolution/offers/${IDS.offer}/accept`);
});

test("approval link shows the exact refund and consents once", async ({ page }) => {
  const m = await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  await page.goto("/approve/tok-1");
  await expect(page.getByRole("heading", { name: "Refund $60.00" })).toBeVisible();
  expect(m.calls).not.toContain("POST /resolution/approvals/tok-1/consent");
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Refund in progress.")).toBeVisible();
});

for (const scheme of ["dark", "light"] as const) {
  test(`case and approval screens are accessible with no banned claims (${scheme})`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await seedReport(page);
    await mockApi(page, { role: "buyer", routes: buyerRoutes() });
    for (const [path, ready] of [
      [`/cases/${IDS.case}`, "Accept offer"],
      ["/approve/tok-1", "Only you can approve."],
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
