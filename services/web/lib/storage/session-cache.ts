import type { z } from "zod";

/**
 * Tab-lifetime cache for server answers that have no read route of their own
 * (a proposal, a cart). It holds no credentials and every read is validated
 * again, so a stale or edited entry just reads as missing. Storage can be
 * blocked, so every call is guarded.
 */
const PREFIX = "ps:";

export function saveEntry(key: string, value: unknown): void {
  try {
    window.sessionStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // Storage is unavailable; the screen falls back to its "ask again" state.
  }
}

export function loadEntry<T>(key: string, schema: z.ZodType<T>): T | null {
  try {
    const raw = window.sessionStorage.getItem(PREFIX + key);
    if (!raw) return null;
    const parsed = schema.safeParse(JSON.parse(raw));
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

export function clearEntry(key: string): void {
  try {
    window.sessionStorage.removeItem(PREFIX + key);
  } catch {
    // Nothing to clear.
  }
}
