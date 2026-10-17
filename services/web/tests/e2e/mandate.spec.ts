import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi } from "./mock-api";
import { buyerRoutes } from "./routes";
import { IDS } from "../mocks/fixtures";
import { BANNED_PHRASES } from "../../lib/honesty/banned";

const serious = async (page: import("@playwright/test").Page) => {
  const r = await new AxeBuilder({ page }).analyze();
  return r.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
};

test("a signed-out visitor to a buyer page is sent to login and returned afterwards", async ({
  page,
}) => {
  await mockApi(page, { role: null, routes: buyerRoutes() });
  await page.goto("/home");
  await expect(page).toHaveURL(/\/login\?next=%2Fhome/);
  await page.getByRole("button", { name: "Start demo session" }).click();
  await expect(page).toHaveURL(/\/home$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Your cap.");
});

test("a merchant on a buyer page sees the wrong-account message", async ({ page }) => {
  await mockApi(page, { role: "merchant", routes: buyerRoutes() });
  await page.goto("/home");
  await expect(page.getByText("Wrong account type")).toBeVisible();
  await expect(page.getByRole("link", { name: "Go to your home" })).toHaveAttribute(
    "href",
    "/merchant",
  );
});

test("buyer home shows mandate, order and case", async ({ page }) => {
  await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  await page.goto("/home");
  await expect(page.getByText("Headphones under $150")).toBeVisible();
  await expect(page.getByRole("link", { name: "View order →" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open case →" })).toBeVisible();
});

test("sign a mandate: preview, read the text, sign, land on the mandate", async ({ page }) => {
  const m = await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  await page.goto("/mandate/new");
  await page.getByLabel(/Northwind/).check();
  await page.getByLabel("What should the agent buy?").fill("Headphones under $150");
  await expect(page.getByRole("button", { name: "Sign mandate" })).toBeDisabled();
  await page.getByRole("button", { name: "Preview terms" }).click();
  await expect(page.getByText("You authorise purchases up to $500.00.")).toBeVisible();
  await page.getByRole("button", { name: "Sign mandate" }).click();
  await expect(page).toHaveURL(new RegExp(`/mandate/${IDS.mandate}$`));
  await expect(page.getByText("Terms as signed")).toBeVisible();
  expect(m.calls.indexOf("POST /mandate/mandates/preview")).toBeLessThan(
    m.calls.indexOf("POST /mandate/mandates"),
  );
});

test("revoke needs a confirmation before anything is sent", async ({ page }) => {
  const m = await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  await page.goto(`/mandate/${IDS.mandate}`);
  await page.getByRole("button", { name: "Revoke mandate" }).click();
  expect(m.calls).not.toContain(`POST /mandate/mandates/${IDS.mandate}/revoke`);
  await page.getByRole("button", { name: "Yes, revoke" }).click();
  await expect(page.getByText("Mandate revoked")).toBeVisible();
});

test.describe("responsive frame", () => {
  test("phone width: bottom tabs, no sideways scroll", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApi(page, { role: "buyer", routes: buyerRoutes() });
    await page.goto("/home");
    const nav = page.getByRole("navigation", { name: "Main" }).filter({ visible: true });
    await expect(nav).toHaveCount(1);
    await expect(nav.getByRole("link", { name: "Orders" })).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test("tablet width: icon rail", async ({ page }) => {
    await page.setViewportSize({ width: 800, height: 900 });
    await mockApi(page, { role: "buyer", routes: buyerRoutes() });
    await page.goto("/home");
    const rail = page.getByRole("navigation", { name: "Main" }).filter({ visible: true });
    await expect(rail).toHaveCount(1);
    const box = await rail.boundingBox();
    expect(box?.width).toBe(72);
  });

  test("desktop width: top navigation", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockApi(page, { role: "buyer", routes: buyerRoutes() });
    await page.goto("/home");
    const top = page.getByRole("navigation", { name: "Main" }).filter({ visible: true });
    await expect(top).toHaveCount(1);
    const box = await top.boundingBox();
    expect(box?.y).toBeLessThan(200);
  });
});

for (const scheme of ["dark", "light"] as const) {
  const pages: [string, string][] = [
    ["/home", "Headphones under $150"],
    ["/mandate/new", "Preview terms"],
    [`/mandate/${IDS.mandate}`, "Terms as signed"],
  ];
  for (const [path, ready] of pages) {
    test(`${path} has no serious accessibility violations and no banned claims (${scheme})`, async ({
      page,
    }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await mockApi(page, { role: "buyer", routes: buyerRoutes() });
      await page.goto(path);
      await page.getByText(ready).first().waitFor();
      expect(await serious(page)).toEqual([]);
      const text = (await page.locator("body").innerText()).toLowerCase();
      expect(BANNED_PHRASES.filter((p) => text.includes(p))).toEqual([]);
    });
  }
}
