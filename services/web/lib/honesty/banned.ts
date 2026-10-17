/**
 * Phrases the product must never claim (PR template checklist). Used by the
 * source scan and the rendered-text crawl in tests. The list lives here and
 * nowhere else.
 */
export const BANNED_PHRASES: readonly string[] = [
  "paypal-backed",
  "paypal backed",
  "verified by paypal",
  "paypal-verified",
  "paypal verified",
  "guaranteed",
  "fraud-proof",
  "injection-proof",
  "compliant",
  "legally binding",
];

export function findBanned(text: string): string[] {
  const lower = text.toLowerCase();
  return BANNED_PHRASES.filter((p) => lower.includes(p));
}
