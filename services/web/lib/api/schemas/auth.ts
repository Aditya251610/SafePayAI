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

export const HANDLE_PATTERN = /^[a-z0-9][a-z0-9_-]{2,31}$/;
export const PASSWORD_MIN = 10;
export const PASSWORD_MAX = 128;

export const signupRequestSchema = z.object({
  handle: z.string().regex(HANDLE_PATTERN),
  password: z.string().min(PASSWORD_MIN).max(PASSWORD_MAX),
  display_name: z.string().trim().min(1).max(64).optional(),
});
export type SignupRequest = z.infer<typeof signupRequestSchema>;
