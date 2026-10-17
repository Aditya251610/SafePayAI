import { apiClient, createClient, type ApiClient, type ClientOptions } from "./client";
import { agentApi } from "./endpoints/agent";
import { auditApi } from "./endpoints/audit";
import { authApi } from "./endpoints/auth";
import { bffApi } from "./endpoints/bff";
import { catalogApi } from "./endpoints/catalog";
import { checkoutApi } from "./endpoints/checkout";
import { mandateApi } from "./endpoints/mandate";
import { opsApi } from "./endpoints/ops";
import { resolutionApi } from "./endpoints/resolution";
import { trackingApi } from "./endpoints/tracking";

export function createApi(client: ApiClient) {
  return {
    auth: authApi(client),
    mandate: mandateApi(client),
    catalog: catalogApi(client),
    agent: agentApi(client),
    checkout: checkoutApi(client),
    tracking: trackingApi(client),
    resolution: resolutionApi(client),
    audit: auditApi(client),
    ops: opsApi(client),
    bff: bffApi(client),
  };
}

export type Api = ReturnType<typeof createApi>;

/** The app-wide API object, bound to the single API_BASE_URL. */
export const api: Api = createApi(apiClient);

export { API_BASE_URL } from "./config";
export { createClient };
export type { ApiClient, ClientOptions };
export * from "./errors";
export * from "./ids";
export * from "./reconcile";
export * from "./schemas";
