/**
 * Display-only money formatting. Amounts are integers in minor units and are
 * never added, subtracted or scaled anywhere in the web app; the server is
 * the only place money is computed.
 */
export function formatMoney(minor: number, currency = "USD", locale = "en-US"): string {
  if (!Number.isSafeInteger(minor)) return "—";
  const digits =
    new Intl.NumberFormat(locale, { style: "currency", currency }).resolvedOptions()
      .maximumFractionDigits ?? 2;
  const negative = minor < 0;
  const abs = String(Math.abs(minor)).padStart(digits + 1, "0");
  const whole = abs.slice(0, abs.length - digits);
  const frac = digits > 0 ? abs.slice(abs.length - digits) : "";
  const formatter = new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  const parts = formatter.formatToParts(0);
  const groupedWhole = new Intl.NumberFormat(locale, { useGrouping: true }).format(BigInt(whole));
  const decimal = parts.find((p) => p.type === "decimal")?.value ?? ".";
  const symbol = parts.find((p) => p.type === "currency")?.value ?? currency;
  const number = digits > 0 ? `${groupedWhole}${decimal}${frac}` : groupedWhole;
  return `${negative ? "-" : ""}${symbol}${number}`;
}
