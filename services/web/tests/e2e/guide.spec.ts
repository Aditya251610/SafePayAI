import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi } from "./mock-api";
import { PUBLIC_ROUTES } from "./routes";
import { BANNED_PHRASES } from "../../lib/honesty/banned";

for (const scheme of ["dark", "light"] as const) {
  for (const path of PUBLIC_ROUTES) {
    test(`${path} is accessible with no banned claims (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await mockApi(page, { role: null });
      await page.goto(path);
      await page.getByRole("heading", { level: 1 }).waitFor();
      if (path === "/login") await page.getByLabel("Account", { exact: true }).waitFor();
      const r = await new AxeBuilder({ page }).analyze();
      expect(r.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual(
        [],
      );
      const text = (await page.locator("body").innerText()).toLowerCase();
      expect(BANNED_PHRASES.filter((p) => text.includes(p))).toEqual([]);
    });
  }
}

test("the guide lists every section and eight steps", async ({ page }) => {
  await mockApi(page, { role: null });
  await page.goto("/guide");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Run the demo.");
  for (const h of [
    "What you are looking at",
    "Before you start",
    "The walkthrough",
    "Who is who",
    "Run it yourself",
    "Honest limits",
  ]) {
    await expect(page.getByRole("heading", { level: 2, name: h })).toBeVisible();
  }
  await expect(page.getByRole("heading", { level: 3 })).toHaveCount(8);
});

test("a step's sign-in button opens the picker with that account chosen", async ({ page }) => {
  await mockApi(page, { role: null });
  await page.goto("/guide");
  await page.getByRole("link", { name: "Sign in as buyer-alex" }).first().click();
  await expect(page).toHaveURL(/\/login\?persona=buyer-alex/);
  await expect(page.getByLabel("Account", { exact: true })).toHaveValue("buyer-alex");
  await page.getByRole("button", { name: /^Sign in as Alex/ }).click();
  await expect(page).toHaveURL(/\/mandate\/new$/);
});

test("the landing nav and the login page link to the guide", async ({ page }) => {
  await mockApi(page, { role: null });
  await page.goto("/");
  await page.getByRole("link", { name: "Run the demo" }).first().click();
  await expect(page).toHaveURL(/\/guide$/);
  await page.goto("/login");
  await expect(page.getByRole("link", { name: "Run the demo" }).first()).toBeVisible();
});

for (const width of [390, 800, 1280]) {
  test(`guide fits a ${width}px window with no sideways scroll`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockApi(page, { role: null });
    await page.goto("/guide");
    await page.getByRole("heading", { level: 1 }).waitFor();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
}
