import { z } from "zod";
import { isoString, roleSchema } from "./common";

export const principalSchema = z.object({
  actor_type: z.string(),
  actor_id: z.string(),
  role: roleSchema,
  display_name: z.string().nullish(),
  merchant_id: z.string().nullish(),
});
export type Principal = z.infer<typeof principalSchema>;

export const sessionResponseSchema = z.object({
  principal: principalSchema,
  expires_at: isoString,
});
export type SessionResponse = z.infer<typeof sessionResponseSchema>;

export const meSchema = z.object({
  actor_type: z.string(),
  actor_id: z.string(),
  role: roleSchema,
  auth_method: z.string(),
  display_name: z.string().nullish(),
  merchant_id: z.string().nullish(),
  session_expires_at: isoString.nullish(),
});
export type Me = z.infer<typeof meSchema>;

export const csrfSchema = z.object({
  csrf_token: z.string().min(1),
  purpose: z.string(),
  expires_at: isoString,
});
export type CsrfToken = z.infer<typeof csrfSchema>;

export const loginRequestSchema = z.object({
  handle: z.string().min(1),
  password: z.string().min(1),
});
export type LoginRequest = z.infer<typeof loginRequestSchema>;
