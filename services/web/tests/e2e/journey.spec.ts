import { test, expect } from "@playwright/test";
import { mockApi } from "./mock-api";
import { buyerRoutes } from "./routes";
import { IDS } from "../mocks/fixtures";

test("the whole buyer journey, from sign-in to an accepted offer", async ({ page }) => {
  await page.route("https://www.sandbox.paypal.com/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/html",
      body: "<title>PayPal sandbox stub</title>",
    }),
  );
  const m = await mockApi(page, { role: null, routes: buyerRoutes() });

  // Sign in as a demo buyer.
  await page.goto("/login");
  await page.getByRole("button", { name: "Start demo session" }).click();
  await expect(page).toHaveURL(/\/home$/);

  // Sign a mandate: preview first, then sign that text.
  await page.getByRole("link", { name: "New mandate" }).click();
  await page.getByLabel(/Northwind/).check();
  await page.getByLabel("What should the agent buy?").fill("Headphones under $150");
  await page.getByRole("button", { name: "Preview terms" }).click();
  await expect(page.getByText("You authorise purchases up to $500.00.")).toBeVisible();
  await page.getByRole("button", { name: "Sign mandate" }).click();
  await expect(page).toHaveURL(new RegExp(`/mandate/${IDS.mandate}$`));

  // Ask the agent, review the draft, build the cart.
  await page.getByRole("link", { name: "State what you need" }).click();
  await page.getByLabel("What do you need?").fill("earbuds under $60");
  await page.getByRole("button", { name: "Propose cart" }).click();
  await expect(page).toHaveURL(/\/agent\/prop-1$/);
  await page.getByRole("button", { name: "Check against my mandate" }).click();
  await expect(page).toHaveURL(new RegExp(`/cart/${IDS.cart}$`));

  // Approve: the order is created and the buyer is sent to the PayPal sandbox.
  await page.getByRole("button", { name: "Approve cart" }).click();
  await expect(page).toHaveURL(/^https:\/\/www\.sandbox\.paypal\.com\//);

  // Back from PayPal: the payment is captured.
  await page.goto("/checkout/return?state=s1&token=TOK&PayerID=PAYER");
  await expect(page.getByText("Payment captured.")).toBeVisible();
  await page.getByRole("link", { name: "Track order" }).click();
  await expect(page).toHaveURL(new RegExp(`/orders/${IDS.order}$`));
  await page.getByRole("link", { name: "Report a problem" }).click();

  // Report it, then accept the offer.
  await page.getByLabel("What went wrong?").fill("It never arrived.");
  await page.getByRole("button", { name: "Open case" }).click();
  await expect(page).toHaveURL(new RegExp(`/cases/${IDS.case}$`));
  await page.getByRole("button", { name: "Accept offer" }).click();
  await expect(page.getByText("Refund in progress.")).toBeVisible();

  const order = [
    "POST /auth/demo-session",
    "POST /mandate/mandates/preview",
    "POST /mandate/mandates",
    "POST /agent/propose",
    "POST /checkout/carts",
    `POST /checkout/carts/${IDS.cart}/confirm`,
    "POST /checkout/orders/return",
    "POST /resolution/cases/report",
    `POST /resolution/offers/${IDS.offer}/accept`,
  ];
  const seen = order.map((c) => m.calls.indexOf(c));
  expect(seen.every((i) => i >= 0)).toBe(true);
  expect([...seen].sort((a, b) => a - b)).toEqual(seen);
});

test("sign-in can be done with the keyboard alone", async ({ page }) => {
  await mockApi(page, { role: null, routes: buyerRoutes() });
  await page.goto("/login");
  const start = page.getByRole("button", { name: "Start demo session" });
  await start.focus();
  await expect(start).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/home$/);
});
