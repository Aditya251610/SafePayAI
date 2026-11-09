import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { callsTo } from "../../mocks/handlers";
import * as f from "../../mocks/fixtures";
import { answer, renderApp } from "./helpers";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => "/shop",
}));
vi.mock("@/lib/api/config", () => ({ API_BASE_URL: "http://gateway.test/api" }));

import { ShopView } from "@/components/shop/shop-view";
import { ProductCard } from "@/components/shop/product-card";
import { catalogItemSchema } from "@/lib/api/schemas/catalog";
import { DEFAULT_FILTERS, filterAndSort } from "@/lib/shop/catalog";

const firstShown = () =>
  filterAndSort(catalogItemSchema.array().parse(f.shopItems()), DEFAULT_FILTERS)[0]!;

beforeEach(() => {
  push.mockClear();
  answer("get", "/catalog/items", 200, f.shopCatalog());
});
afterEach(() => window.sessionStorage.clear());

const addButton = (title: string) => screen.getByRole("button", { name: `Add to basket ${title}` });

describe("ProductCard", () => {
  const item = catalogItemSchema.parse(f.shopItems()[0]);

  it("shows image, tags, price and the mandate hint, and adds the chosen quantity", async () => {
    const onAdd = vi.fn();
    renderApp(
      <ul>
        <ProductCard item={item} maxQtyHint={3} onAdd={onAdd} onOpen={vi.fn()} />
      </ul>,
    );
    expect(screen.getByText("Trailhead")).toBeInTheDocument();
    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByText("$10.00")).toBeInTheDocument();
    expect(screen.getByText(/allows up to 3 per line/)).toBeInTheDocument();
    const img = document.querySelector("img");
    expect(img).toHaveAttribute("src", `/products/${item.sku}.svg`);
    expect(img).toHaveAttribute("width", "640");
    fireEvent.error(img!);
    expect(img).toHaveAttribute("src", "/products/placeholder.svg");
    await userEvent.click(screen.getByRole("button", { name: /Increase quantity/ }));
    await userEvent.click(addButton(item.title));
    expect(onAdd).toHaveBeenCalledWith(item, 2);
  });

  it("stops the stepper at 5", async () => {
    renderApp(
      <ul>
        <ProductCard item={item} onAdd={vi.fn()} onOpen={vi.fn()} />
      </ul>,
    );
    const inc = screen.getByRole("button", { name: /Increase quantity/ });
    for (let i = 0; i < 6; i += 1) await userEvent.click(inc);
    expect(inc).toBeDisabled();
  });
});

describe("ShopView", () => {
  it("lists 24 at a time and loads more", async () => {
    renderApp(<ShopView />);
    expect(await screen.findByText("180 products")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^Add to basket/ })).toHaveLength(24);
    await userEvent.click(screen.getByRole("button", { name: /Load more/ }));
    expect(screen.getAllByRole("button", { name: /^Add to basket/ })).toHaveLength(48);
    expect(callsTo("GET", "/catalog/items")[0]?.search).toContain("limit=200");
  });

  it("searches, filters by chips (with counts) and sorts", async () => {
    renderApp(<ShopView />);
    await screen.findByText("180 products");
    const shops = screen.getByRole("group", { name: "Shop" });
    await userEvent.click(within(shops).getByRole("button", { name: "Hearth (60)" }));
    expect(screen.getByText("60 products")).toBeInTheDocument();
    const cats = screen.getByRole("group", { name: "Category" });
    expect(within(cats).queryByRole("button", { name: /Running/ })).toBeNull();
    await userEvent.click(within(cats).getByRole("button", { name: /^Pantry/ }));
    expect(screen.getByText("15 products")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Search by name"), "item 07");
    expect(screen.getByText("1 product")).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Search by name"));
    await userEvent.type(screen.getByLabelText("Search by name"), "zzz");
    expect(screen.getByText(/Nothing matches/)).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Search by name"));
    await userEvent.selectOptions(screen.getByLabelText("Sort"), "price-desc");
    const prices = screen.getAllByText(/^\$\d+\.\d\d$/).map((e) => e.textContent);
    expect(prices[0]).toBe(
      prices.slice().sort((a, b) => Number(b!.slice(1)) - Number(a!.slice(1)))[0],
    );
  });

  it("adds to the basket, groups by shop, changes quantity, removes and persists", async () => {
    const { unmount } = renderApp(<ShopView />);
    await screen.findByText("180 products");
    const items = f.shopItems();
    const trail = items.find((i) => i.merchant_id === "mrc_trailhead")!;
    const hearth = items.find((i) => i.merchant_id === "mrc_hearth")!;
    await userEvent.type(screen.getByLabelText("Search by name"), trail.title);
    await userEvent.click(addButton(trail.title));
    await userEvent.clear(screen.getByLabelText("Search by name"));
    await userEvent.type(screen.getByLabelText("Search by name"), hearth.title);
    await userEvent.click(addButton(hearth.title));

    const basket = screen.getByRole("complementary", { hidden: true });
    expect(within(basket).getByRole("region", { name: "From Trailhead" })).toBeInTheDocument();
    expect(within(basket).getByRole("region", { name: "From Hearth" })).toBeInTheDocument();
    expect(within(basket).getByText("2 items")).toBeInTheDocument();
    expect(within(basket).getByText(/done by the server, not this page/)).toBeInTheDocument();

    await userEvent.click(
      within(basket).getByRole("button", { name: `Increase quantity of ${trail.title}` }),
    );
    expect(within(basket).getByText("3 items")).toBeInTheDocument();
    expect(JSON.parse(window.sessionStorage.getItem("ps:basket") ?? "{}").lines).toHaveLength(2);

    unmount();
    renderApp(<ShopView />);
    await screen.findByText("180 products");
    const again = screen.getByRole("complementary", { hidden: true });
    expect(within(again).getByText("3 items")).toBeInTheDocument();
    await userEvent.click(within(again).getByRole("button", { name: `Remove ${trail.title}` }));
    expect(within(again).getByText("1 item")).toBeInTheDocument();
  });

  it("creates the cart from the basket against the active mandate and opens it", async () => {
    renderApp(<ShopView />);
    await screen.findByText("180 products");
    const first = firstShown();
    await userEvent.click(addButton(first.title));
    const basket = screen.getByRole("complementary", { hidden: true });
    await userEvent.click(within(basket).getByRole("button", { name: "Check against my mandate" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/cart/${f.IDS.cart}`));
    const call = callsTo("POST", "/checkout/carts")[0];
    expect(call?.body).toEqual({ mandate_id: f.IDS.mandate, lines: [{ sku: first.sku, qty: 1 }] });
    expect(call?.headers["idempotency-key"]).toBeTruthy();
    expect(window.sessionStorage.getItem(`ps:cart:${f.IDS.cart}`)).toContain(f.IDS.mandate);
  });

  it("asks for a mandate first when there is no active one", async () => {
    answer("get", "/bff/buyer-home", 200, { mandates: [], latest_order: null, active_case: null });
    renderApp(<ShopView />);
    await screen.findByText("180 products");
    await userEvent.click(addButton(firstShown().title));
    const basket = screen.getByRole("complementary", { hidden: true });
    expect(await within(basket).findByText("Sign a mandate first")).toBeInTheDocument();
    expect(within(basket).getByRole("link", { name: "Sign a mandate" })).toHaveAttribute(
      "href",
      "/mandate/new",
    );
    expect(within(basket).getByRole("button", { name: "Check against my mandate" })).toBeDisabled();
  });

  it("offers a select when several mandates are active", async () => {
    answer("get", "/bff/buyer-home", 200, {
      mandates: [f.mandate, { ...f.mandate, mandate_id: "22222222-2222-4222-8222-222222222222" }],
      latest_order: null,
      active_case: null,
    });
    renderApp(<ShopView />);
    await screen.findByText("180 products");
    const basket = screen.getByRole("complementary", { hidden: true });
    expect(await within(basket).findByLabelText("Check against")).toBeInTheDocument();
  });

  it("shows a server refusal with a way to try again", async () => {
    answer("post", "/checkout/carts", 503, {
      error: "UPSTREAM_UNAVAILABLE",
      message: "x",
      request_id: "r",
    });
    renderApp(<ShopView />);
    await screen.findByText("180 products");
    await userEvent.click(addButton(firstShown().title));
    const basket = screen.getByRole("complementary", { hidden: true });
    await userEvent.click(within(basket).getByRole("button", { name: "Check against my mandate" }));
    expect(await screen.findByText("Service is unavailable")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("opens a quick view with plain-text description and adds from it", async () => {
    renderApp(<ShopView />);
    await screen.findByText("180 products");
    const first = firstShown();
    await userEvent.click(screen.getByRole("button", { name: `Quick view: ${first.title}` }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: first.title })).toBeInTheDocument();
    expect(within(dialog).getByText(/<b>not html<\/b>/)).toBeInTheDocument();
    expect(dialog.querySelector("b")).toBeNull();
    await userEvent.click(within(dialog).getByRole("button", { name: "Add to basket" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const basket = screen.getByRole("complementary", { hidden: true });
    expect(within(basket).getByText("1 item")).toBeInTheDocument();
  });

  it("closes the quick view with Escape", async () => {
    renderApp(<ShopView />);
    await screen.findByText("180 products");
    await userEvent.click(
      screen.getByRole("button", { name: `Quick view: ${firstShown().title}` }),
    );
    await screen.findByRole("dialog");
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});
