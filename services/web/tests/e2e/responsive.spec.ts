import { test, expect, type Page } from "@playwright/test";
import { mockApi } from "./mock-api";
import { buyerRoutes } from "./routes";
import { IDS, cart, proposal } from "../mocks/fixtures";

async function seed(page: Page) {
  await page.addInitScript(
    ([c, p, r]) => {
      window.sessionStorage.setItem(
        `ps:cart:${(JSON.parse(c as string) as { cart: { cart_id: string } }).cart.cart_id}`,
        c as string,
      );
      window.sessionStorage.setItem("ps:proposal:prop-1", p as string);
      window.sessionStorage.setItem("ps:report:x", r as string);
    },
    [
      JSON.stringify({ cart, mandateId: IDS.mandate }),
      JSON.stringify({ proposal, mandateId: IDS.mandate }),
      "{}",
    ],
  );
}

const BUYER_PAGES: [string, string][] = [
  ["/home", "Headphones under $150"],
  ["/mandate/new", "Preview terms"],
  [`/mandate/${IDS.mandate}`, "Terms as signed"],
  ["/intent", "Agent boundary"],
  ["/agent/prop-1", "Draft · decides nothing"],
  [`/cart/${IDS.cart}`, "Rules decided"],
  ["/orders", "newest first"],
  [`/orders/${IDS.order}`, "Audit chain"],
  [`/orders/${IDS.order}/report`, "AI reads. Rules decide."],
  [`/cases/${IDS.case}`, "Opened by"],
  ["/approve/tok-1", "Only you can approve."],
  ["/audit", "Chain intact"],
];

for (const width of [390, 800, 1280]) {
  test(`buyer screens fit a ${width}px wide window with no sideways scroll`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await seed(page);
    await mockApi(page, { role: "buyer", routes: buyerRoutes() });
    for (const [path, ready] of BUYER_PAGES) {
      await page.goto(path);
      await page.getByText(ready).first().waitFor({ state: "attached" });
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      );
      expect(overflow, `${path} at ${width}px`).toBeLessThanOrEqual(0);
    }
  });
}

test("phone: controls are at least 44px tall", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await seed(page);
  await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  for (const [path, ready] of BUYER_PAGES) {
    await page.goto(path);
    await page.getByText(ready).first().waitFor({ state: "attached" });
    const small = await page.evaluate(() => {
      const els = Array.from(
        document.querySelectorAll<HTMLElement>(
          'button, select, input:not([type="checkbox"]):not([type="hidden"]):not([disabled])',
        ),
      );
      return els
        .filter((e) => e.offsetParent !== null)
        .map((e) => ({
          tag: e.tagName,
          text: (e.textContent ?? "").trim().slice(0, 30),
          h: e.getBoundingClientRect().height,
        }))
        .filter((e) => e.h < 44);
    });
    expect(small, path).toEqual([]);
  }
});

test("phone: the sign button stays reachable above the tab bar", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 700 });
  await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  await page.goto("/mandate/new");
  await page.getByRole("button", { name: "Preview terms" }).waitFor();
  const sign = page.getByRole("button", { name: "Sign mandate" });
  await expect(sign).toBeInViewport();
  const tabs = page.getByRole("navigation", { name: "Main" }).filter({ visible: true });
  const s = await sign.boundingBox();
  const t = await tabs.boundingBox();
  expect((s?.y ?? 0) + (s?.height ?? 0)).toBeLessThanOrEqual((t?.y ?? 0) + 1);
});

test("phone: the approve button stays reachable on the cart", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 700 });
  await seed(page);
  await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  await page.goto(`/cart/${IDS.cart}`);
  await page.getByText("Rules decided").waitFor();
  await expect(page.getByRole("button", { name: "Approve cart" })).toBeInViewport();
});

test("tablet: the orders list opens a split view", async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 800 });
  await mockApi(page, { role: "buyer", routes: buyerRoutes() });
  await page.goto("/orders");
  await expect(page.getByTestId("order-pane")).toBeVisible();
  await expect(page.getByRole("table")).toBeHidden();
  await expect(page.getByText("Simulated carrier").first()).toBeVisible();
});

test("staff screens ask for a larger screen on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const [role, path] of [
    ["operator", "/ops"],
    ["reviewer", "/review"],
  ] as const) {
    await mockApi(page, { role, routes: buyerRoutes() });
    await page.goto(path);
    await expect(page.getByText("Use a larger screen")).toBeVisible();
    await page.unroute("**/api/**");
  }
});
