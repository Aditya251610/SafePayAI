import { describe, expect, it, vi } from "vitest";
import { HttpResponse } from "msw";
import { z } from "zod";
import { server } from "../../mocks/server";
import { TEST_BASE, calls, callsTo, recorded } from "../../mocks/handlers";
import {
  AmbiguousOutcomeError,
  ApiError,
  ContractMismatchError,
  NetworkError,
  createClient,
} from "@/lib/api";

const okSchema = z.object({ ok: z.boolean() });
const noSleep = () => Promise.resolve();

function client(extra: Parameters<typeof createClient>[0] = {}) {
  return createClient({ baseUrl: TEST_BASE, sleep: noSleep, ...extra });
}

describe("API base URL", () => {
  it("defaults to the single /api base", async () => {
    const { API_BASE_URL } = await import("@/lib/api/config");
    expect(API_BASE_URL).toBe("/api");
    expect(createClient().baseUrl).toBe("/api");
  });
});

describe("GET", () => {
  it("sends credentials and parses the response with the schema", async () => {
    server.use(recorded("get", "/x", () => HttpResponse.json({ ok: true })));
    await expect(client().get("/x", okSchema)).resolves.toEqual({ ok: true });
  });

  it("does not send CSRF or idempotency headers", async () => {
    server.use(recorded("get", "/x", () => HttpResponse.json({ ok: true })));
    await client().get("/x", okSchema);
    expect(callsTo("GET", "/auth/csrf")).toHaveLength(0);
  });

  it("throws ContractMismatchError when the body does not match", async () => {
    server.use(recorded("get", "/x", () => HttpResponse.json({ nope: 1 })));
    const err = await client()
      .get("/x", okSchema)
      .catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ContractMismatchError);
    expect((err as ContractMismatchError).code).toBe("CONTRACT_MISMATCH");
  });

  it("throws a normalised ApiError on non-2xx", async () => {
    server.use(
      recorded("get", "/x", () =>
        HttpResponse.json(
          { error: "FORBIDDEN", detail: "no", message: "no", request_id: "r" },
          { status: 403 },
        ),
      ),
    );
    const err = (await client()
      .get("/x", okSchema)
      .catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("FORBIDDEN");
    expect(err.status).toBe(403);
  });

  it("calls onUnauthenticated on 401", async () => {
    const spy = vi.fn();
    server.use(
      recorded("get", "/x", () =>
        HttpResponse.json({ error: "UNAUTHENTICATED", message: "login" }, { status: 401 }),
      ),
    );
    await client({ onUnauthenticated: spy })
      .get("/x", okSchema)
      .catch(() => undefined);
    expect(spy).toHaveBeenCalledOnce();
  });

  it("retries 503 UPSTREAM_WAKING with backoff, then succeeds", async () => {
    let n = 0;
    const sleeps: number[] = [];
    server.use(
      recorded("get", "/x", () => {
        n += 1;
        return n < 3
          ? HttpResponse.json({ error: "UPSTREAM_WAKING", message: "waking" }, { status: 503 })
          : HttpResponse.json({ ok: true });
      }),
    );
    const c = client({ sleep: (ms) => (sleeps.push(ms), Promise.resolve()) });
    await expect(c.get("/x", okSchema)).resolves.toEqual({ ok: true });
    expect(n).toBe(3);
    expect(sleeps).toEqual([1000, 2000]);
  });

  it("gives up waking retries after the backoff list is spent", async () => {
    let n = 0;
    server.use(
      recorded("get", "/x", () => {
        n += 1;
        return HttpResponse.json({ error: "UPSTREAM_WAKING", message: "waking" }, { status: 503 });
      }),
    );
    const err = (await client()
      .get("/x", okSchema)
      .catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe("UPSTREAM_WAKING");
    expect(n).toBe(5);
  });

  it("maps a dropped connection to NetworkError", async () => {
    server.use(recorded("get", "/x", () => HttpResponse.error()));
    await expect(client().get("/x", okSchema)).rejects.toBeInstanceOf(NetworkError);
  });
});

describe("POST", () => {
  it("fetches a fresh single-use CSRF token before every call", async () => {
    server.use(recorded("post", "/y", () => HttpResponse.json({ ok: true })));
    const c = client();
    await c.send("/y", okSchema, { body: { a: 1 } });
    await c.send("/y", okSchema, { body: { a: 2 } });
    const tokens = callsTo("POST", "/y").map((r) => r.headers["x-csrf-token"]);
    expect(tokens).toHaveLength(2);
    expect(tokens[0]).toBeTruthy();
    expect(tokens[0]).not.toBe(tokens[1]);
    expect(callsTo("GET", "/auth/csrf")).toHaveLength(2);
  });

  it("requests the given CSRF purpose", async () => {
    server.use(recorded("post", "/y", () => HttpResponse.json({ ok: true })));
    await client().send("/y", okSchema, { csrfPurpose: "ops_freeze" });
    expect(callsTo("GET", "/auth/csrf")[0]?.search).toBe("?purpose=ops_freeze");
  });

  it("skips CSRF when noCsrf is set", async () => {
    server.use(recorded("post", "/y", () => HttpResponse.json({ ok: true })));
    await client().send("/y", okSchema, { noCsrf: true });
    expect(callsTo("GET", "/auth/csrf")).toHaveLength(0);
  });

  it("adds a distinct Idempotency-Key per submit and none on non-idempotent routes", async () => {
    server.use(recorded("post", "/y", () => HttpResponse.json({ ok: true })));
    const c = client();
    await c.send("/y", okSchema, { idempotent: true });
    await c.send("/y", okSchema, { idempotent: true });
    await c.send("/y", okSchema, {});
    const keys = callsTo("POST", "/y").map((r) => r.headers["idempotency-key"]);
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBeTruthy();
    expect(keys[0]).not.toBe(keys[1]);
    expect(keys[2]).toBeUndefined();
  });

  it("reuses a caller-supplied key for caller retries", async () => {
    server.use(recorded("post", "/y", () => HttpResponse.json({ ok: true })));
    const c = client();
    await c.send("/y", okSchema, { idempotent: true, idempotencyKey: "k-1" });
    await c.send("/y", okSchema, { idempotent: true, idempotencyKey: "k-1" });
    expect(callsTo("POST", "/y").map((r) => r.headers["idempotency-key"])).toEqual(["k-1", "k-1"]);
  });

  it("retries once on CSRF_INVALID with a fresh token and the same key", async () => {
    let n = 0;
    server.use(
      recorded("post", "/y", () => {
        n += 1;
        return n === 1
          ? HttpResponse.json(
              { error: "CSRF_INVALID", detail: "x", message: "x", request_id: "r" },
              { status: 403 },
            )
          : HttpResponse.json({ ok: true });
      }),
    );
    await expect(client().send("/y", okSchema, { idempotent: true })).resolves.toEqual({
      ok: true,
    });
    const posts = callsTo("POST", "/y");
    expect(posts).toHaveLength(2);
    expect(posts[0]?.headers["x-csrf-token"]).not.toBe(posts[1]?.headers["x-csrf-token"]);
    expect(posts[0]?.headers["idempotency-key"]).toBe(posts[1]?.headers["idempotency-key"]);
  });

  it("does not retry CSRF_INVALID a second time", async () => {
    server.use(
      recorded("post", "/y", () =>
        HttpResponse.json({ error: "CSRF_INVALID", detail: "x", message: "x" }, { status: 403 }),
      ),
    );
    const err = (await client()
      .send("/y", okSchema)
      .catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe("CSRF_INVALID");
    expect(callsTo("POST", "/y")).toHaveLength(2);
  });

  it("never retries a POST on UPSTREAM_WAKING", async () => {
    server.use(
      recorded("post", "/y", () =>
        HttpResponse.json({ error: "UPSTREAM_WAKING", message: "w" }, { status: 503 }),
      ),
    );
    const err = (await client()
      .send("/y", okSchema)
      .catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe("UPSTREAM_WAKING");
    expect(callsTo("POST", "/y")).toHaveLength(1);
  });

  it("treats 504 on a money route as an ambiguous outcome and does not retry", async () => {
    server.use(
      recorded("post", "/y", () =>
        HttpResponse.json(
          { error: "UPSTREAM_TIMEOUT", message: "t", request_id: "r9" },
          { status: 504 },
        ),
      ),
    );
    const err = (await client()
      .send("/y", okSchema, { money: true, idempotent: true })
      .catch((e: unknown) => e)) as AmbiguousOutcomeError;
    expect(err).toBeInstanceOf(AmbiguousOutcomeError);
    expect(err.code).toBe("OUTCOME_UNKNOWN");
    expect(err.requestId).toBe("r9");
    expect(callsTo("POST", "/y")).toHaveLength(1);
  });

  it("treats a dropped connection on a money route as ambiguous", async () => {
    server.use(recorded("post", "/y", () => HttpResponse.error()));
    await expect(client().send("/y", okSchema, { money: true })).rejects.toBeInstanceOf(
      AmbiguousOutcomeError,
    );
  });

  it("treats 504 on a non-money route as a plain error", async () => {
    server.use(
      recorded("post", "/y", () =>
        HttpResponse.json({ error: "UPSTREAM_TIMEOUT", message: "t" }, { status: 504 }),
      ),
    );
    const err = (await client()
      .send("/y", okSchema)
      .catch((e: unknown) => e)) as ApiError;
    expect(err).not.toBeInstanceOf(AmbiguousOutcomeError);
    expect(err.code).toBe("UPSTREAM_TIMEOUT");
  });

  it("surfaces MONEY_ROUTES_DISABLED as a normal error", async () => {
    server.use(
      recorded("post", "/y", () =>
        HttpResponse.json({ error: "MONEY_ROUTES_DISABLED", message: "off" }, { status: 503 }),
      ),
    );
    const err = (await client()
      .send("/y", okSchema, { money: true })
      .catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe("MONEY_ROUTES_DISABLED");
  });

  it("accepts an empty 204 body for a void schema", async () => {
    server.use(recorded("post", "/y", () => new HttpResponse(null, { status: 204 })));
    await expect(client().send("/y", z.undefined(), { noCsrf: true })).resolves.toBeUndefined();
  });

  it("sends JSON bodies with the right content type", async () => {
    server.use(recorded("post", "/y", () => HttpResponse.json({ ok: true })));
    await client().send("/y", okSchema, { body: { hello: "world" } });
    const call = callsTo("POST", "/y")[0];
    expect(call?.body).toEqual({ hello: "world" });
    expect(call?.headers["content-type"]).toContain("application/json");
  });

  it("does not fetch a CSRF token for GETs", async () => {
    server.use(recorded("get", "/x", () => HttpResponse.json({ ok: true })));
    await client().get("/x", okSchema);
    expect(calls.some((c) => c.path === "/auth/csrf")).toBe(false);
  });
});
