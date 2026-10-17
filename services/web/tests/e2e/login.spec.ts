import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi } from "./mock-api";

test("landing links to sign in and the story content is present", async ({ page }) => {
  await mockApi(page, { role: null });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Set the cap.");
  for (const scene of ["Sign the", "The agent proposes.", "6 days late.", "Rules decide."]) {
    await expect(page.getByText(scene, { exact: false }).first()).toBeAttached();
  }
  await page.getByRole("link", { name: "Sign your first mandate" }).first().click();
  await expect(page).toHaveURL(/\/login$/);
});

test("demo session signs in and lands on the buyer home", async ({ page }) => {
  await mockApi(page, { role: null });
  await page.goto("/login?next=%2Fhome");
  await page.getByRole("button", { name: "Start demo session" }).click();
  await expect(page).toHaveURL(/\/home$/);
});

test("staff sign-in goes to the role's home", async ({ page }) => {
  await mockApi(page, { role: null });
  await page.goto("/login");
  await page.getByLabel("Handle").fill("operator");
  await page.getByLabel("Password").fill("pw");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/ops$/);
});

test("wrong staff credentials show a clear message and stay put", async ({ page }) => {
  await mockApi(page, { role: null });
  await page.goto("/login");
  await page.getByLabel("Handle").fill("operator");
  await page.getByLabel("Password").fill("nope");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Handle or password was not accepted.")).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test("a full demo shows the capacity message", async ({ page }) => {
  await mockApi(page, { role: null, demoStatus: 503 });
  await page.goto("/login");
  await page.getByRole("button", { name: "Start demo session" }).click();
  await expect(page.getByText("Service is unavailable")).toBeVisible();
});

test("rate limiting shows a countdown", async ({ page }) => {
  await mockApi(page, { role: null, demoStatus: 429 });
  await page.goto("/login");
  await page.getByRole("button", { name: "Start demo session" }).click();
  await expect(page.getByText(/Try again in \d+s\./)).toBeVisible();
});

test("a signed-in visitor is sent straight to their home", async ({ page }) => {
  await mockApi(page, { role: "buyer" });
  await page.goto("/login");
  await expect(page).toHaveURL(/\/home$/);
});

for (const scheme of ["dark", "light"] as const) {
  test(`login has no serious accessibility violations (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await mockApi(page, { role: null });
    await page.goto("/login");
    const results = await new AxeBuilder({ page }).analyze();
    expect(
      results.violations.filter((v) => v.impact === "serious" || v.impact === "critical"),
    ).toEqual([]);
  });
}

test("unsafe next paths are ignored", async ({ page }) => {
  await mockApi(page, { role: null });
  await page.goto("/login?next=https%3A%2F%2Fevil.test");
  await page.getByRole("button", { name: "Start demo session" }).click();
  await expect(page).toHaveURL(/\/home$/);
});
