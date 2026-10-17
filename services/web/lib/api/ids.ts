import { InvalidIdError } from "./errors";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: unknown): value is string {
  return typeof value === "string" && UUID.test(value);
}

/**
 * The gateway answers 500 on a malformed UUID path segment, so every id is
 * checked here before a request is built.
 */
export function requireUuid(value: string, label: string): string {
  if (!isUuid(value)) throw new InvalidIdError(label);
  return value;
}

/** For opaque path segments such as approval tokens. */
export function pathSegment(value: string, label: string): string {
  if (value.length === 0) throw new InvalidIdError(label);
  return encodeURIComponent(value);
}

export function newIdempotencyKey(): string {
  return globalThis.crypto.randomUUID();
}
