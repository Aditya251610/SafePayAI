import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi } from "./mock-api";
import { buyerRoutes } from "./routes";
import { IDS, cart } from "../mocks/fixtures";
import { BANNED_PHRASES } from "../../lib/honesty/banned";

async function seedCart(page: Page, over: Record<string, unknown> = {}) {
  await page.addInitScript(
    ([key, value]) => window.sessionStorage.setItem(key as string, value as string),
    [`ps:cart:${IDS.cart}`, JSON.stringify({ cart: { ...cart, ...over }, mandateId: IDS.mandate })],
  );
}

async function stubPayPal(page: Page) {
  await page.route("https://www.sandbox.paypal.com/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/html",
      body: "<title>PayPal sandbox stub</title><p>stub</p>",
    }),
  );
}

test("approve a cart: order is created, then the buyer is sent to PayPal's sandbox", async ({
  page,
}) => {
  await seedCart(page);
  await stubPayPal(page);
  const m = await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  await page.goto(`/cart/${IDS.cart}`);
  await expect(page.getByText("Rules decided")).toBeVisible();
  await page.getByRole("button", { name: "Approve cart" }).click();
  await expect(page).toHaveURL(/^https:\/\/www\.sandbox\.paypal\.com\//);
  expect(m.calls).toContain(`POST /checkout/carts/${IDS.cart}/confirm`);
});

test("a blocked cart cannot be approved", async ({ page }) => {
  await seedCart(page, {
    status: "BLOCKED",
    checks: [
      { name: "mandate_evaluate", result: "BLOCK", reason_code: "OVER_CAP", source: "mandate" },
    ],
  });
  const m = await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  await page.goto(`/cart/${IDS.cart}`);
  await expect(page.getByRole("button", { name: "Approve cart" })).toBeDisabled();
  expect(m.calls).not.toContain(`POST /checkout/carts/${IDS.cart}/confirm`);
});

test("coming back from PayPal captures the payment and cleans the address bar", async ({
  page,
}) => {
  const m = await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  await page.goto("/checkout/return?state=s1&token=TOK&PayerID=PAYER");
  await expect(page.getByText("Payment captured.")).toBeVisible();
  await expect(page).toHaveURL(/\/checkout\/return$/);
  expect(m.calls.filter((c) => c === "POST /checkout/orders/return")).toHaveLength(1);
});

test("leaving PayPal records the cancellation", async ({ page }) => {
  await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  await page.goto("/checkout/cancel?state=c1");
  await expect(page.getByText("You left PayPal. The order was cancelled.")).toBeVisible();
});

for (const scheme of ["dark", "light"] as const) {
  test(`cart and payment screens are accessible with no banned claims (${scheme})`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await seedCart(page, { status: "NEEDS_CONFIRMATION" });
    await mockApi(page, { role: "buyer", routes: buyerRoutes() });
    for (const [path, ready] of [
      [`/cart/${IDS.cart}`, "Rules decided"],
      ["/checkout/return?state=s1&token=TOK&PayerID=PAYER", "Payment captured."],
      ["/checkout/cancel?state=c1", "You left PayPal. The order was cancelled."],
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
