import type { ApiClient } from "../client";
import {
  opsStatusSchema,
  freezeRequestSchema,
  wakeSchema,
  type FreezeRequest,
} from "../schemas/ops";
import { refundsFrozenStateSchema } from "../schemas/resolution";
import { parseBody } from "./validate";

export function opsApi(c: ApiClient) {
  return {
    status: async (signal?: AbortSignal) => c.get("/ops/status", opsStatusSchema, { signal }),
    /**
     * Public, harmless ping that starts sleeping backend hosts waking. Fire and forget:
     * any failure is swallowed and resolves to null, so it can never block or show an error.
     */
    wake: async (signal?: AbortSignal) => {
      try {
        return await c.get("/wake", wakeSchema, { signal });
      } catch {
        return null;
      }
    },
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
