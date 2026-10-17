export const METER_CELLS = 20;

/**
 * Number of filled cells (0..20) for a bar that shows `part` of `whole`.
 * This is a picture of a ratio, never shown as a number and never fed back
 * into any money value, so it lives apart from the *_minor arithmetic ban.
 */
export function meterCells(part: number, whole: number, cells = METER_CELLS): number {
  if (!Number.isFinite(part) || !Number.isFinite(whole) || whole <= 0 || part <= 0) return 0;
  if (part >= whole) return cells;
  return Math.max(1, Math.round((part / whole) * cells));
}
