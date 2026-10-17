const CHECK_NAME: Record<string, string> = {
  catalog_resolve: "Catalog price lookup",
  price_mismatch: "Catalog price match",
  mandate_evaluate: "Mandate rules",
};

/** Human name for a policy check. Unknown names are shown as the server sent them. */
export function checkLabel(name: string): string {
  return CHECK_NAME[name] ?? name.replace(/_/g, " ");
}

const REASON: Record<string, string> = {
  OVER_CAP: "Over the cap",
  MERCHANT_NOT_ALLOWED: "Shop is not on the allowlist",
  QTY_CAP: "Too many of one item",
  UNKNOWN_SKU: "Item is not in the catalog",
  CURRENCY_MISMATCH: "Currency does not match",
  PRICE_MISMATCH: "Price differs from the catalog",
  CART_ARITHMETIC_MISMATCH: "Totals do not add up",
  MANDATE_INTEGRITY_FAILED: "Mandate failed its integrity check",
  MANDATE_REVOKED: "Mandate was revoked",
  MANDATE_EXPIRED: "Mandate has expired",
  MANDATE_EXHAUSTED: "Cap is used up",
  CATALOG_UNAVAILABLE: "Catalog could not be reached",
  MANDATE_UNAVAILABLE: "Mandate could not be reached",
};

export function reasonLabel(code: string | null | undefined): string | null {
  if (!code) return null;
  return REASON[code] ?? code;
}
