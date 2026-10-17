import type { Page } from "@playwright/test";
import * as f from "../mocks/fixtures";

type Role = "buyer" | "merchant" | "operator" | "reviewer";

export interface MockResponse {
  status?: number;
  body?: unknown;
  headers?: Record<string, string>;
}

export interface MockOptions {
  /** Role the session starts with; null means signed out. */
  role: Role | null;
  /** Make demo-session answer with this status instead of creating a buyer. */
  demoStatus?: number;
  /** Extra answers keyed "METHOD /path" (path without /api). They win over the defaults. */
  routes?: Record<string, MockResponse | ((body: unknown) => MockResponse)>;
}

/**
 * Answers every /api call in the browser. Sign-in routes change the role so
 * the next /auth/me reflects it.
 */
export async function mockApi(
  page: Page,
  opts: MockOptions,
): Promise<{ role: () => Role | null; calls: string[] }> {
  let role = opts.role;
  const calls: string[] = [];
  await page.route("**/api/**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname.replace(/^\/api/, "");
    const key = `${req.method()} ${path}`;
    calls.push(key);
    const json = (status: number, body: unknown, headers?: Record<string, string>) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
        headers,
      });

    const extra = opts.routes?.[key];
    if (extra) {
      let body: unknown;
      try {
        body = req.postDataJSON();
      } catch {
        body = undefined;
      }
      const r = typeof extra === "function" ? extra(body) : extra;
      if (r.status === 204) return route.fulfill({ status: 204 });
      return json(r.status ?? 200, r.body ?? {}, r.headers);
    }

    if (path === "/auth/me") {
      if (!role)
        return json(401, { error: "UNAUTHENTICATED", message: "Sign in", request_id: "e2e" });
      return json(200, { ...f.me, role, display_name: `demo-${role}` });
    }
    if (path === "/auth/csrf")
      return json(200, f.csrf(url.searchParams.get("purpose") ?? "general"));
    if (path === "/auth/logout") {
      role = null;
      return route.fulfill({ status: 204 });
    }
    if (path === "/auth/demo-session") {
      if (opts.demoStatus && opts.demoStatus !== 201) {
        return json(
          opts.demoStatus,
          opts.demoStatus === 429
            ? { error: "RATE_LIMITED", message: "slow", request_id: "e2e" }
            : { error: "UPSTREAM_UNAVAILABLE", message: "full", request_id: "e2e" },
          opts.demoStatus === 429 ? { "Retry-After": "30" } : undefined,
        );
      }
      role = "buyer";
      return json(201, f.session);
    }
    if (path === "/auth/login") {
      const body = req.postDataJSON() as { handle?: string; password?: string };
      if (body.handle === "operator" && body.password === "pw") {
        role = "operator";
        return json(200, { principal: { ...f.principal, role: "operator" }, expires_at: f.ISO });
      }
      return json(401, {
        error: "UNAUTHENTICATED",
        detail: "UNAUTHENTICATED",
        message: "no",
        request_id: "e2e",
      });
    }
    return json(404, { error: "NOT_FOUND", message: "not mocked", request_id: "e2e" });
  });
  return { role: () => role, calls };
}
