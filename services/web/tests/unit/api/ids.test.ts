import { describe, expect, it } from "vitest";
import { InvalidIdError, isUuid, newIdempotencyKey, pathSegment, requireUuid } from "@/lib/api";

describe("ids", () => {
  it("recognises UUIDs", () => {
    expect(isUuid("11111111-1111-4111-8111-111111111111")).toBe(true);
    expect(isUuid("preview")).toBe(false);
    expect(isUuid(42)).toBe(false);
  });

  it("rejects a non-UUID before any request is built", () => {
    expect(() => requireUuid("preview", "mandate id")).toThrow(InvalidIdError);
  });

  it("encodes opaque path segments and rejects empty ones", () => {
    expect(pathSegment("a/b c", "token")).toBe("a%2Fb%20c");
    expect(() => pathSegment("", "token")).toThrow(InvalidIdError);
  });

  it("generates distinct idempotency keys", () => {
    expect(newIdempotencyKey()).not.toBe(newIdempotencyKey());
  });
});
