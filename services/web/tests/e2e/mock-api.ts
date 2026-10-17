import type { Page } from "@playwright/test";
import * as f from "../mocks/fixtures";

type Role = "buyer" | "merchant" | "operator" | "reviewer";

/**
 * Answers every /api call in the browser. `role` null means signed out.
 * Extra routes can be added per test with page.route before navigation.
 */
export async function mockApi(page: Page, role: Role | null): Promise<void> {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    const json = (status: number, body: unknown) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (path === "/auth/me") {
      if (!role)
        return json(401, { error: "UNAUTHENTICATED", message: "Sign in", request_id: "e2e" });
      return json(200, { ...f.me, role, display_name: `demo-${role}` });
    }
    if (path === "/auth/csrf")
      return json(200, f.csrf(url.searchParams.get("purpose") ?? "general"));
    if (path === "/auth/logout") return route.fulfill({ status: 204 });
    return json(404, { error: "NOT_FOUND", message: "not mocked", request_id: "e2e" });
  });
}
