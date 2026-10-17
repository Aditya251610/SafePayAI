import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";
import { clearEntry, loadEntry, saveEntry } from "@/lib/storage/session-cache";
import { loadCart, loadProposal, saveCart, saveProposal } from "@/lib/storage/entries";
import * as f from "../mocks/fixtures";
import { cartSchema } from "@/lib/api/schemas/checkout";
import { proposalSchema } from "@/lib/api/schemas/agent";

afterEach(() => {
  window.sessionStorage.clear();
  vi.restoreAllMocks();
});

const schema = z.object({ n: z.number() });

describe("session cache", () => {
  it("round-trips a validated value", () => {
    saveEntry("a", { n: 1 });
    expect(loadEntry("a", schema)).toEqual({ n: 1 });
    clearEntry("a");
    expect(loadEntry("a", schema)).toBeNull();
  });
  it("treats a tampered or malformed entry as missing", () => {
    window.sessionStorage.setItem("ps:a", JSON.stringify({ n: "x" }));
    expect(loadEntry("a", schema)).toBeNull();
    window.sessionStorage.setItem("ps:a", "{not json");
    expect(loadEntry("a", schema)).toBeNull();
  });
  it("survives blocked storage", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => saveEntry("a", { n: 1 })).not.toThrow();
    expect(loadEntry("a", schema)).toBeNull();
    expect(() => clearEntry("a")).not.toThrow();
  });
  it("stores proposals and carts by their ids", () => {
    const proposal = proposalSchema.parse(f.proposal);
    const cart = cartSchema.parse(f.cart);
    saveProposal({ proposal, mandateId: f.IDS.mandate });
    saveCart({ cart, mandateId: f.IDS.mandate });
    expect(loadProposal("prop-1")?.proposal.lines[0]?.sku).toBe("SKU-1");
    expect(loadCart(f.IDS.cart)?.cart.total_minor).toBe(4820);
    expect(loadProposal("other")).toBeNull();
  });
});
