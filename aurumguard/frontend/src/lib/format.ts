export function fmtNum(n: number | null | undefined, digits = 2, locale = "en"): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "n/a";
  return new Intl.NumberFormat(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
}
export function fmtPct(n: number | null | undefined, digits = 1, locale = "en"): string {
  if (n === null || n === undefined) return "n/a";
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(n)}%`;
}
export function fmtTime(iso: string | null | undefined, tz = "UTC", locale = "en", withDate = true): string {
  if (!iso) return "n/a";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "n/a";
  try {
    return new Intl.DateTimeFormat(locale, { timeZone: tz, ...(withDate ? { year: "numeric", month: "short", day: "2-digit" } : {}), hour: "2-digit", minute: "2-digit", hour12: false, timeZoneName: "short" }).format(d);
  } catch { return d.toISOString(); }
}
export function countdown(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "n/a";
  const ms = new Date(iso).getTime() - now;
  if (Number.isNaN(ms)) return "n/a";
  const sign = ms < 0 ? "-" : "";
  const s = Math.abs(Math.floor(ms / 1000));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  if (h >= 48) return `${sign}${Math.floor(h / 24)}d ${h % 24}h`;
  return `${sign}${h}h ${String(m).padStart(2, "0")}m`;
}
export function statusLabel(s: string): string { return s.replace(/_/g, " "); }
