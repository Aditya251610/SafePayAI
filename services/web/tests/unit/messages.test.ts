import { describe, expect, it } from "vitest";
import { KNOWN_ERROR_CODES, errorCopy } from "@/lib/api/messages";
import { findBanned } from "@/lib/honesty/banned";

describe("error copy", () => {
  it("has plain text for every known code", () => {
    expect(KNOWN_ERROR_CODES.length).toBeGreaterThan(30);
    for (const code of KNOWN_ERROR_CODES) {
      const c = errorCopy(code);
      expect(c.title.length, code).toBeGreaterThan(3);
      expect(c.text.length, code).toBeGreaterThan(10);
      expect(findBanned(`${c.title} ${c.text}`), code).toEqual([]);
    }
  });
  it("covers every gateway code from the integration contract", () => {
    for (const code of [
      "UNAUTHENTICATED",
      "FORBIDDEN",
      "CSRF_INVALID",
      "NOT_FOUND",
      "RATE_LIMITED",
      "IDEMPOTENCY_KEY_REQUIRED",
      "MONEY_ROUTES_DISABLED",
      "UPSTREAM_UNAVAILABLE",
      "UPSTREAM_WAKING",
      "UPSTREAM_TIMEOUT",
      "UPSTREAM_BAD_RESPONSE",
      "validation_error",
      "internal_error",
    ]) {
      expect(KNOWN_ERROR_CODES, code).toContain(code);
    }
  });
  it("falls back for codes it does not know", () => {
    expect(errorCopy("SOMETHING_NEW").title).toBe("Something went wrong");
  });
  it("does not tell people a payment failed when the outcome is unknown", () => {
    expect(errorCopy("OUTCOME_UNKNOWN").text).toMatch(/may have gone through/);
    expect(errorCopy("OUTCOME_UNKNOWN").retryable).toBe(false);
  });
});
