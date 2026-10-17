function toDate(iso: string): Date | null {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatDateTime(iso: string, locale = "en-US", timeZone?: string): string {
  const d = toDate(iso);
  if (!d) return "—";
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone,
  }).format(d);
}

export function formatDate(iso: string, locale = "en-US", timeZone?: string): string {
  const d = toDate(iso);
  if (!d) return "—";
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeZone }).format(d);
}
