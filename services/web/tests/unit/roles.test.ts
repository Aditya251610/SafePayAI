import { describe, expect, it } from "vitest";
import { canAccess, homeFor, isAllowedApproveUrl, safeNextPath } from "@/lib/auth/roles";

describe("roles", () => {
  it("sends each role to its own home", () => {
    expect(homeFor("buyer")).toBe("/home");
    expect(homeFor("merchant")).toBe("/merchant");
    expect(homeFor("operator")).toBe("/ops");
    expect(homeFor("reviewer")).toBe("/review");
  });
  it("gates routes by role", () => {
    expect(canAccess("buyer", "/orders/abc")).toBe(true);
    expect(canAccess("merchant", "/orders")).toBe(false);
    expect(canAccess("merchant", "/merchant/cases/1")).toBe(true);
    expect(canAccess("operator", "/merchant")).toBe(true);
    expect(canAccess("buyer", "/ops")).toBe(false);
    expect(canAccess("reviewer", "/review")).toBe(true);
    expect(canAccess("buyer", "/audit")).toBe(true);
    expect(canAccess("reviewer", "/audit")).toBe(true);
  });
  it("leaves public routes open", () => {
    expect(canAccess("buyer", "/")).toBe(true);
    expect(canAccess("buyer", "/login")).toBe(true);
  });
  it("does not match on a shared prefix", () => {
    expect(canAccess("buyer", "/operations")).toBe(true);
  });
  it("accepts only same-origin relative next paths", () => {
    expect(safeNextPath("/orders/1", "/home")).toBe("/orders/1");
    expect(safeNextPath("https://evil.test", "/home")).toBe("/home");
    expect(safeNextPath("//evil.test", "/home")).toBe("/home");
    expect(safeNextPath("/\\evil", "/home")).toBe("/home");
    expect(safeNextPath(null, "/home")).toBe("/home");
  });
  it("guards the PayPal approve redirect", () => {
    const hosts = ["www.sandbox.paypal.com"];
    expect(isAllowedApproveUrl("https://www.sandbox.paypal.com/checkoutnow?token=1", hosts)).toBe(
      true,
    );
    expect(isAllowedApproveUrl("http://www.sandbox.paypal.com/x", hosts)).toBe(false);
    expect(isAllowedApproveUrl("https://www.sandbox.paypal.com.evil.test/x", hosts)).toBe(false);
    expect(isAllowedApproveUrl("javascript:alert(1)", hosts)).toBe(false);
    expect(isAllowedApproveUrl("not a url", hosts)).toBe(false);
  });
});
