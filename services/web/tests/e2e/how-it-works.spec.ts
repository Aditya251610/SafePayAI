import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi } from "./mock-api";
import { BANNED_PHRASES } from "../../lib/honesty/banned";

test("the landing page links to the PayPal and AI story", async ({ page }) => {
  await mockApi(page, { role: null });
  await page.goto("/");
  await page.getByRole("link", { name: "PayPal and AI", exact: true }).click();
  await expect(page).toHaveURL(/\/how-it-works$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Where PayPal fits.");
});

test("the story names every actor and the AI boundary", async ({ page }) => {
  await mockApi(page, { role: null });
  await page.goto("/how-it-works");
  await expect(page.getByText("AI classifies and drafts. It never decides money.")).toBeVisible();
  await expect(
    page.getByText("On any error or low confidence it hands the case to a person."),
  ).toBeVisible();
  await expect(page.getByRole("heading", { level: 3 })).toHaveCount(7);
  await expect(page.getByText("Simulated carrier").first()).toBeAttached();
  await expect(page.getByText("PayPal sandbox order").first()).toBeAttached();
});

for (const scheme of ["dark", "light"] as const) {
  test(`how it works is accessible with no banned claims (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await mockApi(page, { role: null });
    await page.goto("/how-it-works");
    await page.getByRole("heading", { level: 1 }).waitFor();
    const r = await new AxeBuilder({ page }).analyze();
    expect(r.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual(
      [],
    );
    const text = (await page.locator("body").innerText()).toLowerCase();
    expect(BANNED_PHRASES.filter((p) => text.includes(p))).toEqual([]);
  });
}

for (const width of [390, 800, 1280]) {
  test(`how it works fits a ${width}px window with no sideways scroll`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockApi(page, { role: null });
    await page.goto("/how-it-works");
    await page.getByRole("heading", { level: 1 }).waitFor();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
}
