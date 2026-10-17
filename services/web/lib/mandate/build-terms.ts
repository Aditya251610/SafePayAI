import type { MandateTermsInput } from "@/lib/api/schemas/mandate";
import { merchantLabel } from "@/lib/format/label";
import { parseMoneyInput } from "@/lib/format/money-input";

export interface MandateFormState {
  cap: string;
  perLine: string;
  /** datetime-local value in the buyer's own zone. */
  ends: string;
  merchants: string[];
  intent: string;
  late: boolean;
  lost: boolean;
  maxRefund: string;
  deliverDays: string;
}

export type FormErrors = Partial<Record<keyof MandateFormState, string>>;

/** datetime-local string for `date`, e.g. "2026-10-30T12:00". */
export function toLocalInput(date: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}T${p(date.getHours())}:${p(date.getMinutes())}`;
}

/** The server wants "YYYY-MM-DDTHH:MM:SSZ". */
export function toServerTimestamp(localInput: string): string | null {
  const d = new Date(localInput);
  if (Number.isNaN(d.getTime())) return null;
  return `${d.toISOString().slice(0, 19)}Z`;
}

export function defaultFormState(now: Date = new Date()): MandateFormState {
  const ends = new Date(now.getTime());
  ends.setDate(ends.getDate() + 14);
  return {
    cap: "500.00",
    perLine: "5",
    ends: toLocalInput(ends),
    merchants: [],
    intent: "",
    late: true,
    lost: true,
    maxRefund: "150.00",
    deliverDays: "7",
  };
}

export const INTENT_MAX = 500;

/** Maps the server's field names to form fields so bounds errors land on the right input. */
export const SERVER_FIELD_TO_FORM: Readonly<Record<string, keyof MandateFormState>> = {
  max_total_minor: "cap",
  max_qty_per_line: "perLine",
  expires_at: "ends",
  merchant_allowlist: "merchants",
  intent_text: "intent",
  "protection.max_refund_minor": "maxRefund",
  "protection.deliver_by_days": "deliverDays",
  "protection.kinds_covered": "late",
};

/** Turn the form into the request body, or say which fields need work. */
export function buildTerms(
  s: MandateFormState,
): { terms: MandateTermsInput; errors: null } | { terms: null; errors: FormErrors } {
  const errors: FormErrors = {};

  const cap = parseMoneyInput(s.cap);
  if (cap === null || cap <= 0) errors.cap = "Enter an amount above zero, like 500.00.";

  const refund = parseMoneyInput(s.maxRefund);
  if (refund === null || refund <= 0) errors.maxRefund = "Enter an amount above zero, like 150.00.";

  let perLine: number | null = null;
  if (s.perLine.trim() !== "") {
    const n = Number(s.perLine);
    if (!Number.isInteger(n) || n < 1)
      errors.perLine = "Use a whole number, 1 or more, or leave it empty.";
    else perLine = n;
  }

  const days = Number(s.deliverDays);
  if (!Number.isInteger(days) || days < 1 || days > 30) {
    errors.deliverDays = "Use a whole number of days from 1 to 30.";
  }

  const ends = toServerTimestamp(s.ends);
  if (!s.ends || ends === null) errors.ends = "Pick an end date and time.";

  if (s.merchants.length < 1) errors.merchants = "Tick at least one shop.";
  if (s.merchants.length > 5) errors.merchants = "Pick at most five shops.";

  const intent = s.intent.trim();
  if (intent.length < 1) errors.intent = "Say in plain words what the agent should buy.";
  else if (intent.length > INTENT_MAX) errors.intent = `Keep it under ${INTENT_MAX} characters.`;
  else if (/[\n\r\t]/.test(intent)) errors.intent = "Use one line, no tabs.";

  if (!s.late && !s.lost) errors.late = "Cover at least one of late or lost.";

  if (Object.keys(errors).length > 0 || cap === null || refund === null || ends === null) {
    return { terms: null, errors };
  }

  const kinds: ("LATE" | "LOST")[] = [];
  if (s.late) kinds.push("LATE");
  if (s.lost) kinds.push("LOST");

  const terms: MandateTermsInput = {
    currency: "USD",
    max_total_minor: cap,
    merchant_allowlist: s.merchants.map((id) => ({
      merchant_id: id,
      display_name: merchantLabel(id).slice(0, 64) || id,
    })),
    intent_text: intent,
    expires_at: ends,
    protection: { kinds_covered: kinds, max_refund_minor: refund, deliver_by_days: days },
    ...(perLine !== null ? { max_qty_per_line: perLine } : {}),
  };
  return { terms, errors: null };
}
