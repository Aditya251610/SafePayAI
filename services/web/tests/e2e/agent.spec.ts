import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi } from "./mock-api";
import { buyerRoutes } from "./routes";
import { IDS, proposal } from "../mocks/fixtures";
import { BANNED_PHRASES } from "../../lib/honesty/banned";

async function seedProposal(page: Page) {
  await page.addInitScript(
    ([key, value]) => window.sessionStorage.setItem(key as string, value as string),
    ["ps:proposal:prop-1", JSON.stringify({ proposal, mandateId: IDS.mandate })],
  );
}

test("ask in words, review the draft, build the cart", async ({ page }) => {
  const m = await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  await page.goto("/intent");
  await page.getByLabel("What do you need?").fill("earbuds under $60");
  await page.getByRole("button", { name: "Propose cart" }).click();
  await expect(page).toHaveURL(/\/agent\/prop-1$/);
  await expect(page.getByText("Draft · decides nothing")).toBeVisible();
  await expect(page.getByText("Wired earbuds")).toBeVisible();
  await page.getByRole("button", { name: "Check against my mandate" }).click();
  await expect(page).toHaveURL(new RegExp(`/cart/${IDS.cart}$`));
  expect(m.calls.indexOf("POST /agent/propose")).toBeLessThan(
    m.calls.indexOf("POST /checkout/carts"),
  );
});

test("form mode asks with a category and a budget", async ({ page }) => {
  await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  await page.goto("/intent?mode=form");
  await page.getByLabel("Category").selectOption("audio");
  await page.getByLabel("Budget (USD)").fill("60");
  await page.getByRole("button", { name: "Propose cart" }).click();
  await expect(page).toHaveURL(/\/agent\/prop-1$/);
});

test("no match leaves the buyer with another way forward", async ({ page }) => {
  await mockApi(page, {
    role: "buyer",
    routes: {
      ...buyerRoutes(),
      "POST /agent/propose": {
        body: {
          ...proposal,
          status: "NO_MATCH",
          lines: [],
          no_match_reason: "Nothing under that budget.",
        },
      },
    },
  });
  await page.goto("/intent");
  await page.getByLabel("What do you need?").fill("gold watch");
  await page.getByRole("button", { name: "Propose cart" }).click();
  await expect(page.getByText("Nothing matched")).toBeVisible();
  await expect(page.getByRole("link", { name: "Use the form" })).toBeVisible();
});

test("a reloaded proposal that is gone says so", async ({ page }) => {
  await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  await page.goto("/agent/prop-1");
  await expect(page.getByText("This proposal is no longer here")).toBeVisible();
});

for (const scheme of ["dark", "light"] as const) {
  test(`intent and agent pages are accessible with no banned claims (${scheme})`, async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await seedProposal(page);
    await mockApi(page, { role: "buyer", routes: buyerRoutes() });
    for (const [path, ready] of [
      ["/intent", "Agent boundary"],
      ["/agent/prop-1", "Draft · decides nothing"],
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
