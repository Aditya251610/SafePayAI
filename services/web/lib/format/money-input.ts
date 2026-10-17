/**
 * Turn what a buyer typed ("500", "500.5", "1,250.00") into integer minor
 * units without floating point. Returns null for anything else. This is the
 * only place the app converts a typed amount; the server still validates it.
 */
export function parseMoneyInput(text: string, fractionDigits = 2): number | null {
  const cleaned = text.trim().replace(/[$,\s]/g, "");
  const m = /^(\d{1,9})(?:\.(\d*))?$/.exec(cleaned);
  if (!m) return null;
  const whole = m[1] ?? "0";
  const frac = m[2] ?? "";
  if (frac.length > fractionDigits) return null;
  const padded = frac.padEnd(fractionDigits, "0");
  const value = Number(`${whole}${padded}`);
  return Number.isSafeInteger(value) ? value : null;
}
