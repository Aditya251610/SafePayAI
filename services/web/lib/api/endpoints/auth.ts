import { z } from "zod";
import type { ApiClient } from "../client";
import { parseBody } from "./validate";
import {
  demoPersonaRequestSchema,
  demoPersonasSchema,
  loginRequestSchema,
  meSchema,
  sessionResponseSchema,
  signupRequestSchema,
  type LoginRequest,
  type SignupRequest,
} from "../schemas/auth";

export function authApi(c: ApiClient) {
  return {
    demoSession: async (signal?: AbortSignal) =>
      c.send("/auth/demo-session", sessionResponseSchema, { noCsrf: true, signal }),
    /** Seeded accounts for the picker. 404 when the deployment has them switched off. */
    demoPersonas: async (signal?: AbortSignal) =>
      c.get("/auth/demo-personas", demoPersonasSchema, { signal }),
    /** Sign in as a seeded account by handle; no password, no CSRF. 404 if off or not allowed. */
    demoPersona: async (handle: string, signal?: AbortSignal) =>
      c.send("/auth/demo-persona", sessionResponseSchema, {
        noCsrf: true,
        body: parseBody(demoPersonaRequestSchema, { handle }),
        signal,
      }),
    login: async (input: LoginRequest, signal?: AbortSignal) =>
      c.send("/auth/login", sessionResponseSchema, {
        noCsrf: true,
        body: loginRequestSchema.parse(input),
        signal,
      }),
    /** Self-service buyer account; no CSRF, like login. 409 HANDLE_TAKEN, 422 invalid. */
    signup: async (input: SignupRequest, signal?: AbortSignal) =>
      c.send("/auth/signup", sessionResponseSchema, {
        noCsrf: true,
        body: parseBody(signupRequestSchema, input),
        signal,
      }),
    logout: async (signal?: AbortSignal) =>
      c.send("/auth/logout", z.undefined(), { noCsrf: true, signal }),
    me: async (signal?: AbortSignal) => c.get("/auth/me", meSchema, { signal }),
  };
}
