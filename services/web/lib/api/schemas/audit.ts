import { z } from "zod";
import { isoString } from "./common";

export const auditRowSchema = z.object({
  seq: z.number().int(),
  recorded_at: isoString,
  event_type: z.string(),
  actor_type: z.string(),
  actor_id: z.string(),
  auth_method: z.string().nullish(),
  request_id: z.string().nullish(),
  mandate_id: z.string().nullish(),
  order_id: z.string().nullish(),
  case_id: z.string().nullish(),
  summary: z.string(),
  row_hash_short: z.string(),
  prev_hash_short: z.string(),
});
export type AuditRow = z.infer<typeof auditRowSchema>;

export const auditEntriesSchema = z.object({
  rows: z.array(auditRowSchema),
  lastRow: z.number().int(),
  head_seq: z.number().int(),
});
export type AuditEntries = z.infer<typeof auditEntriesSchema>;

export interface AuditEntriesQuery {
  limit?: number;
  after_seq?: number;
  before_seq?: number;
  event_type?: string;
  mandate_id?: string;
  order_id?: string;
  case_id?: string;
  sort?: string;
}

export const auditVerifySchema = z.object({
  ok: z.boolean(),
  chain_id: z.string().nullish(),
  checked: z.number().int().nullish(),
  head_seq: z.number().int().nullish(),
  head_hash: z.string().nullish(),
  algorithm: z.string().nullish(),
  duration_ms: z.number().nullish(),
  anchor: z.object({ checked: z.boolean(), ok: z.boolean().nullish() }).nullish(),
  first_bad_seq: z.number().int().nullish(),
  reason: z.string().nullish(),
  expected: z.string().nullish(),
  found: z.string().nullish(),
});
export type AuditVerify = z.infer<typeof auditVerifySchema>;
