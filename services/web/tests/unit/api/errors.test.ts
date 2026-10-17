import { describe, expect, it } from "vitest";
import { normalizeError } from "@/lib/api/errors";

const h = (v?: string) => ({
  get: (n: string) => (n.toLowerCase() === "retry-after" ? (v ?? null) : null),
});

describe("normalizeError", () => {
  it("reads gateway-native uppercase codes", () => {
    const e = normalizeError(403, {
      error: "CSRF_INVALID",
      detail: "bad token",
      message: "bad token",
      request_id: "r1",
    });
    expect(e.code).toBe("CSRF_INVALID");
    expect(e.message).toBe("bad token");
    expect(e.requestId).toBe("r1");
  });

  it("reads mandate's nested error object", () => {
    const e = normalizeError(422, {
      error: {
        code: "TERMS_OUT_OF_BOUNDS",
        message: "too big",
        details: { field: "max_total_minor" },
      },
      request_id: "r2",
    });
    expect(e.code).toBe("TERMS_OUT_OF_BOUNDS");
    expect(e.message).toBe("too big");
    expect(e.requestId).toBe("r2");
  });

  it("takes resolution's real code from detail when error is http_error", () => {
    const e = normalizeError(404, {
      error: "http_error",
      detail: "CASE_NOT_FOUND",
      request_id: "r3",
    });
    expect(e.code).toBe("CASE_NOT_FOUND");
  });

  it("keeps checkout's flat code and human detail", () => {
    const e = normalizeError(404, {
      error: "ORDER_NOT_FOUND",
      detail: "order not found",
      request_id: "r4",
      details: {},
    });
    expect(e.code).toBe("ORDER_NOT_FOUND");
    expect(e.message).toBe("order not found");
  });

  it("uses the uppercase detail when a service lowercases the code", () => {
    const e = normalizeError(401, {
      error: "unauthenticated",
      detail: "UNAUTHENTICATED",
      request_id: "r5",
    });
    expect(e.code).toBe("UNAUTHENTICATED");
  });

  it("keeps validation_error and exposes field issues from a 422 list", () => {
    const e = normalizeError(422, {
      error: "validation_error",
      detail: [{ loc: ["body", "terms", "currency"], msg: "Field required", type: "missing" }],
      request_id: "r6",
    });
    expect(e.code).toBe("validation_error");
    expect(e.fields).toEqual([{ field: "terms.currency", message: "Field required" }]);
  });

  it("handles the bff shape with only error and message", () => {
    const e = normalizeError(404, { error: "ORDER_NOT_FOUND", message: "order not found" });
    expect(e.code).toBe("ORDER_NOT_FOUND");
    expect(e.requestId).toBeNull();
  });

  it("handles gateway errors that have no detail field", () => {
    const e = normalizeError(400, {
      error: "IDEMPOTENCY_KEY_REQUIRED",
      message: "key needed",
      request_id: "r7",
    });
    expect(e.code).toBe("IDEMPOTENCY_KEY_REQUIRED");
    expect(e.message).toBe("key needed");
  });

  it("reads Retry-After", () => {
    const e = normalizeError(429, { error: "RATE_LIMITED", message: "slow down" }, h("12"));
    expect(e.retryAfterS).toBe(12);
  });

  it("falls back to UNKNOWN for non-JSON or unrecognised bodies", () => {
    expect(normalizeError(500, undefined).code).toBe("UNKNOWN");
    expect(normalizeError(502, "<html>").code).toBe("UNKNOWN");
    expect(normalizeError(500, { foo: 1 }).code).toBe("UNKNOWN");
  });
});
