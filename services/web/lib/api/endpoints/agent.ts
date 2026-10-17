import type { ApiClient } from "../client";
import { proposalSchema, proposeRequestSchema, type ProposeRequest } from "../schemas/agent";
import { parseBody } from "./validate";

export function agentApi(c: ApiClient) {
  return {
    propose: async (
      input: ProposeRequest,
      opts: { idempotencyKey?: string; signal?: AbortSignal } = {},
    ) =>
      c.send("/agent/propose", proposalSchema, {
        body: parseBody(proposeRequestSchema, input),
        idempotent: true,
        idempotencyKey: opts.idempotencyKey,
        signal: opts.signal,
      }),
  };
}
