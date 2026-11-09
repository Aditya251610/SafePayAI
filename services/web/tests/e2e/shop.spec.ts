import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi } from "./mock-api";
import { buyerRoutes } from "./routes";
import { IDS, shopCatalog, shopItems } from "../mocks/fixtures";
import { BANNED_PHRASES } from "../../lib/honesty/banned";

function shopRoutes() {
  return { ...buyerRoutes(), "GET /catalog/items": { body: shopCatalog() } };
}

test("browse, filter, add, check against the mandate and land on the cart", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  const m = await mockApi(page, { role: "buyer", routes: shopRoutes() });
  await page.goto("/shop");
  await expect(page.getByText("180 products")).toBeVisible();

  await page
    .getByRole("group", { name: "Shop" })
    .getByRole("button", { name: "Pixelwire (60)" })
    .click();
  await expect(page.getByText("60 products")).toBeVisible();
  await page.getByLabel("Search by name").fill("item 03");
  const target = shopItems().find(
    (i) => i.merchant_id === "mrc_pixelwire" && i.sku.endsWith("-03"),
  )!;
  await page.getByRole("button", { name: `Add to basket ${target.title}` }).click();

  const basket = page.getByRole("complementary");
  await expect(basket.getByText("1 item")).toBeVisible();
  await basket.getByRole("button", { name: "Check against my mandate" }).click();
  await expect(page).toHaveURL(new RegExp(`/cart/${IDS.cart}$`));
  expect(m.calls).toContain("POST /checkout/carts");
  expect(m.calls).toContain("GET /wake");
});

for (const scheme of ["dark", "light"] as const) {
  test(`shop is accessible with no banned claims (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await mockApi(page, { role: "buyer", routes: shopRoutes() });
    await page.goto("/shop");
    await expect(page.getByText("180 products")).toBeVisible();
    const r = await new AxeBuilder({ page }).analyze();
    expect(r.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual(
      [],
    );
    const text = (await page.locator("body").innerText()).toLowerCase();
    expect(BANNED_PHRASES.filter((p) => text.includes(p))).toEqual([]);
  });
}

for (const width of [390, 800, 1280]) {
  test(`shop fits a ${width}px window with no sideways scroll`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockApi(page, { role: "buyer", routes: shopRoutes() });
    await page.goto("/shop");
    await expect(page.getByText("180 products")).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
}
