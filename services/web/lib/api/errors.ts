/**
 * Error model. Every non-2xx response is reduced to one ApiError whose `code`
 * is what the UI branches on. The gateway and the services behind it return
 * different envelope shapes (contract section 4), so the normaliser below is
 * the only place that knows about them.
 */

export interface FieldIssue {
  field: string;
  message: string;
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId: string | null;
  readonly retryAfterS: number | null;
  readonly fields: FieldIssue[];

  constructor(init: {
    code: string;
    message: string;
    status: number;
    requestId?: string | null;
    retryAfterS?: number | null;
    fields?: FieldIssue[];
  }) {
    super(init.message);
    this.name = "ApiError";
    this.code = init.code;
    this.status = init.status;
    this.requestId = init.requestId ?? null;
    this.retryAfterS = init.retryAfterS ?? null;
    this.fields = init.fields ?? [];
  }
}

/**
 * A money route (confirm, capture, accept, consent, freeze) timed out or the
 * connection dropped. The backend may still have completed the action, so the
 * caller must read the real state and never retry the POST blindly.
 */
export class AmbiguousOutcomeError extends ApiError {
  constructor(init: ConstructorParameters<typeof ApiError>[0]) {
    super(init);
    this.name = "AmbiguousOutcomeError";
  }
}

/** The server answered 2xx with a body that does not match the expected shape. */
export class ContractMismatchError extends ApiError {
  readonly issues: string[];
  constructor(path: string, issues: string[], requestId: string | null) {
    super({
      code: "CONTRACT_MISMATCH",
      message: `Unexpected response shape from ${path}`,
      status: 200,
      requestId,
    });
    this.name = "ContractMismatchError";
    this.issues = issues;
  }
}

/** The request never produced an HTTP response. */
export class NetworkError extends ApiError {
  constructor(message = "Network request failed") {
    super({ code: "NETWORK_ERROR", message, status: 0 });
    this.name = "NetworkError";
  }
}

/** A path id was not a UUID; rejected before any request is made. */
export class InvalidIdError extends ApiError {
  constructor(label: string) {
    super({ code: "INVALID_ID", message: `${label} is not a valid id`, status: 0 });
    this.name = "InvalidIdError";
  }
}

const UPPER_CODE = /^[A-Z][A-Z0-9_]+$/;

type Json = Record<string, unknown>;

function isRecord(v: unknown): v is Json {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function str(v: unknown): string | null {
  return typeof v === "string" && v.length > 0 ? v : null;
}

function issuesFrom(detail: unknown): FieldIssue[] {
  if (!Array.isArray(detail)) return [];
  const out: FieldIssue[] = [];
  for (const item of detail) {
    if (!isRecord(item)) continue;
    const loc = Array.isArray(item.loc) ? item.loc.filter((p) => p !== "body").join(".") : "";
    out.push({ field: loc, message: str(item.msg) ?? "Invalid value" });
  }
  return out;
}

export function parseRetryAfter(value: string | null): number | null {
  if (!value) return null;
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 ? Math.ceil(n) : null;
}

/**
 * Reduce any error response to { code, message, ... }.
 *
 *  - gateway-native:   { error: "UPPER", detail, message, request_id }
 *  - mandate:          { error: { code, message, details }, request_id }
 *  - resolution:       { error: "http_error", detail: "CODE", request_id }
 *  - shopping-agent:   { error: "lowercase", detail: "UPPER", request_id }
 *  - 422 validation:   { error: "validation_error", detail: [ { loc, msg } ], request_id }
 *  - bff:              { error, message }
 */
export function normalizeError(
  status: number,
  body: unknown,
  headers?: { get(name: string): string | null },
): ApiError {
  const retryAfterS = parseRetryAfter(headers?.get("Retry-After") ?? null);
  const fallback = status >= 500 ? "Something went wrong on our side." : "The request failed.";

  if (!isRecord(body)) {
    return new ApiError({ code: "UNKNOWN", message: fallback, status, retryAfterS });
  }

  const requestId = str(body.request_id);
  const rawError = body.error;
  const detail = body.detail;
  const detailStr = str(detail);

  let code = "UNKNOWN";
  let message: string | null = str(body.message);
  let fields: FieldIssue[] = [];

  if (isRecord(rawError)) {
    code = str(rawError.code) ?? code;
    message = message ?? str(rawError.message);
  } else if (typeof rawError === "string") {
    if (rawError === "http_error" && detailStr) {
      code = detailStr;
    } else if (rawError === rawError.toLowerCase() && detailStr && UPPER_CODE.test(detailStr)) {
      code = detailStr;
    } else {
      code = rawError;
    }
  } else if (detailStr && UPPER_CODE.test(detailStr)) {
    code = detailStr;
  }

  if (Array.isArray(detail)) fields = issuesFrom(detail);
  message = message ?? (detailStr && !UPPER_CODE.test(detailStr) ? detailStr : null);

  return new ApiError({
    code,
    message: message ?? fallback,
    status,
    requestId,
    retryAfterS,
    fields,
  });
}
