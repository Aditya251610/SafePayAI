import { z } from "zod";
import type { ApiClient } from "../client";
import {
  loginRequestSchema,
  meSchema,
  sessionResponseSchema,
  type LoginRequest,
} from "../schemas/auth";

export function authApi(c: ApiClient) {
  return {
    demoSession: async (signal?: AbortSignal) =>
      c.send("/auth/demo-session", sessionResponseSchema, { noCsrf: true, signal }),
    login: async (input: LoginRequest, signal?: AbortSignal) =>
      c.send("/auth/login", sessionResponseSchema, {
        noCsrf: true,
        body: loginRequestSchema.parse(input),
        signal,
      }),
    logout: async (signal?: AbortSignal) =>
      c.send("/auth/logout", z.undefined(), { noCsrf: true, signal }),
    me: async (signal?: AbortSignal) => c.get("/auth/me", meSchema, { signal }),
  };
}
