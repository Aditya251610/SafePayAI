import type { ApiClient } from "../client";
import { opsStatusSchema, freezeRequestSchema, type FreezeRequest } from "../schemas/ops";
import { refundsFrozenStateSchema } from "../schemas/resolution";
import { parseBody } from "./validate";

export function opsApi(c: ApiClient) {
  return {
    status: async (signal?: AbortSignal) => c.get("/ops/status", opsStatusSchema, { signal }),
    /** Operator only. Money-gated; uses the ops_freeze CSRF purpose. */
    freeze: async (input: FreezeRequest, signal?: AbortSignal) =>
      c.send("/ops/freeze", refundsFrozenStateSchema, {
        body: parseBody(freezeRequestSchema, input),
        csrfPurpose: "ops_freeze",
        money: true,
        signal,
      }),
  };
}
