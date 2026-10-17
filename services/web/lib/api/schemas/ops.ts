import { z } from "zod";

export const opsStatusSchema = z.object({
  demo_mode: z.boolean(),
  money_routes_enabled: z.boolean(),
  refunds_frozen: z.enum(["true", "false", "unknown"]),
  build_id: z.string(),
});
export type OpsStatus = z.infer<typeof opsStatusSchema>;

export const freezeRequestSchema = z.object({
  frozen: z.boolean(),
  reason: z.string().trim().min(1),
});
export type FreezeRequest = z.infer<typeof freezeRequestSchema>;
