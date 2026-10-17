import type { ApiClient } from "../client";
import { auditEntriesSchema, auditVerifySchema, type AuditEntriesQuery } from "../schemas/audit";

export function auditApi(c: ApiClient) {
  return {
    /** Page with after_seq or before_seq; startRow does not offset the query upstream. */
    entries: async (query: AuditEntriesQuery = {}, signal?: AbortSignal) =>
      c.get("/audit/entries", auditEntriesSchema, {
        query: {
          endRow: query.limit,
          after_seq: query.after_seq,
          before_seq: query.before_seq,
          event_type: query.event_type,
          mandate_id: query.mandate_id,
          order_id: query.order_id,
          case_id: query.case_id,
          sort: query.sort,
        },
        signal,
      }),
    verify: async (signal?: AbortSignal) => c.get("/audit/verify", auditVerifySchema, { signal }),
  };
}
