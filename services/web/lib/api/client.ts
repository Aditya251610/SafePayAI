import type { z } from "zod";
import { API_BASE_URL } from "./config";
import {
  AmbiguousOutcomeError,
  ApiError,
  ContractMismatchError,
  NetworkError,
  normalizeError,
} from "./errors";
import { newIdempotencyKey } from "./ids";
import { csrfSchema } from "./schemas/auth";

export interface ClientOptions {
  /** Defaults to the single API_BASE_URL. Tests pass an absolute URL. */
  baseUrl?: string;
  fetch?: typeof fetch;
  newKey?: () => string;
  sleep?: (ms: number) => Promise<void>;
  /** Called on any 401 so the app can drop its session state. */
  onUnauthenticated?: () => void;
  /** Delays between retries of an idempotent GET while the backend wakes. */
  wakingBackoffMs?: readonly number[];
}

export interface ReadOptions {
  query?: Record<string, string | number | boolean | undefined>;
  signal?: AbortSignal;
}

export interface SendOptions {
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
  signal?: AbortSignal;
  /** Route requires an Idempotency-Key header. */
  idempotent?: boolean;
  /** Reuse a key across caller-side retries of the same submit. */
  idempotencyKey?: string;
  /** CSRF purpose; every route uses "general" except ops freeze. */
  csrfPurpose?: string;
  /** Money-moving route: a 504 or dropped connection is an ambiguous outcome. */
  money?: boolean;
  method?: "POST" | "PUT";
  /** Route needs no CSRF token (login, demo-session, logout). */
  noCsrf?: boolean;
}

export interface ApiClient {
  readonly baseUrl: string;
  get<T>(path: string, schema: z.ZodType<T>, opts?: ReadOptions): Promise<T>;
  send<T>(path: string, schema: z.ZodType<T>, opts?: SendOptions): Promise<T>;
}

const DEFAULT_WAKING_BACKOFF_MS = [1000, 2000, 4000, 8000] as const;

interface RawResponse {
  status: number;
  ok: boolean;
  headers: Headers;
  body: unknown;
  unparseable: boolean;
}

function buildUrl(
  baseUrl: string,
  path: string,
  query?: Record<string, string | number | boolean | undefined>,
): string {
  const url = `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined) params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

export function createClient(options: ClientOptions = {}): ApiClient {
  const baseUrl = (options.baseUrl ?? API_BASE_URL).replace(/\/+$/, "");
  const doFetch = options.fetch ?? ((...a: Parameters<typeof fetch>) => globalThis.fetch(...a));
  const newKey = options.newKey ?? newIdempotencyKey;
  const sleep = options.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  const backoff = options.wakingBackoffMs ?? DEFAULT_WAKING_BACKOFF_MS;

  async function raw(url: string, init: RequestInit): Promise<RawResponse> {
    let res: Response;
    try {
      res = await doFetch(url, { ...init, credentials: "include" });
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
      throw new NetworkError();
    }
    const text = await res.text();
    if (text.length === 0) {
      return {
        status: res.status,
        ok: res.ok,
        headers: res.headers,
        body: undefined,
        unparseable: false,
      };
    }
    try {
      return {
        status: res.status,
        ok: res.ok,
        headers: res.headers,
        body: JSON.parse(text) as unknown,
        unparseable: false,
      };
    } catch {
      return {
        status: res.status,
        ok: res.ok,
        headers: res.headers,
        body: undefined,
        unparseable: true,
      };
    }
  }

  function toError(res: RawResponse): ApiError {
    const err = normalizeError(res.status, res.body, res.headers);
    if (res.status === 401) options.onUnauthenticated?.();
    return err;
  }

  function parse<T>(path: string, schema: z.ZodType<T>, res: RawResponse): T {
    const requestId =
      typeof res.body === "object" && res.body !== null && "request_id" in res.body
        ? String((res.body as { request_id: unknown }).request_id)
        : null;
    if (res.unparseable)
      throw new ContractMismatchError(path, ["response was not JSON"], requestId);
    const parsed = schema.safeParse(res.body);
    if (!parsed.success) {
      throw new ContractMismatchError(
        path,
        parsed.error.issues.map((i) => `${i.path.join(".") || "(root)"}: ${i.message}`),
        requestId,
      );
    }
    return parsed.data;
  }

  async function fetchCsrf(purpose: string, signal?: AbortSignal): Promise<string> {
    const url = buildUrl(baseUrl, "/auth/csrf", { purpose });
    const res = await raw(url, { method: "GET", headers: { Accept: "application/json" }, signal });
    if (!res.ok) throw toError(res);
    return parse("/auth/csrf", csrfSchema, res).csrf_token;
  }

  return {
    baseUrl,

    async get<T>(path: string, schema: z.ZodType<T>, opts: ReadOptions = {}): Promise<T> {
      const url = buildUrl(baseUrl, path, opts.query);
      for (let attempt = 0; ; attempt += 1) {
        const res = await raw(url, {
          method: "GET",
          headers: { Accept: "application/json" },
          signal: opts.signal,
        });
        if (res.ok) return parse(path, schema, res);
        const err = toError(res);
        // Only idempotent reads are retried while the backend wakes up.
        if (err.code === "UPSTREAM_WAKING" && attempt < backoff.length) {
          await sleep(backoff[attempt] ?? 1000);
          continue;
        }
        throw err;
      }
    },

    async send<T>(path: string, schema: z.ZodType<T>, opts: SendOptions = {}): Promise<T> {
      const method = opts.method ?? "POST";
      const url = buildUrl(baseUrl, path, opts.query);
      const key = opts.idempotent ? (opts.idempotencyKey ?? newKey()) : undefined;

      let res: RawResponse | null = null;
      for (let attempt = 0; attempt < 2; attempt += 1) {
        const headers: Record<string, string> = { Accept: "application/json" };
        if (!opts.noCsrf) {
          headers["X-CSRF-Token"] = await fetchCsrf(opts.csrfPurpose ?? "general", opts.signal);
        }
        if (key) headers["Idempotency-Key"] = key;
        let body: string | undefined;
        if (opts.body !== undefined) {
          headers["Content-Type"] = "application/json";
          body = JSON.stringify(opts.body);
        }

        try {
          res = await raw(url, { method, headers, body, signal: opts.signal });
        } catch (cause) {
          if (opts.money && cause instanceof NetworkError) {
            throw new AmbiguousOutcomeError({
              code: "OUTCOME_UNKNOWN",
              message: "The connection dropped. The action may have completed.",
              status: 0,
            });
          }
          throw cause;
        }

        if (res.ok) return parse(path, schema, res);

        const err = toError(res);
        // Tokens are single-use; a bad one gets one retry with a fresh token and the same key.
        if (err.code === "CSRF_INVALID" && attempt === 0) continue;
        if (opts.money && res.status === 504) {
          throw new AmbiguousOutcomeError({
            code: "OUTCOME_UNKNOWN",
            message: "The request timed out. The action may have completed.",
            status: 504,
            requestId: err.requestId,
          });
        }
        throw err;
      }
      // Unreachable: the loop either returns or throws.
      throw new NetworkError();
    },
  };
}

/** Shared default client used by the app. */
export const apiClient: ApiClient = createClient();
