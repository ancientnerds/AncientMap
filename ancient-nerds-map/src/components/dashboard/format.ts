/** Number and time formatting shared by the dashboard panels (German locale, UTC hours). */

export function fmtInt(n: number): string {
  return n.toLocaleString('de-DE')
}

/** Share of `part` in `whole` as "37 %"; "0 %" when there is nothing to divide by. */
export function fmtShare(part: number, whole: number): string {
  return `${whole ? Math.round((part / whole) * 100) : 0} %`
}

/** "14 Uhr" for a UTC hour of the day. */
export function fmtHour(hour: number): string {
  return `${String(hour).padStart(2, '0')} Uhr`
}

/** "17.09. 14:05" in UTC — the founders compare against Umami, which shows UTC too. */
export function fmtStamp(iso: string): string {
  const d = new Date(iso)
  const dd = String(d.getUTCDate()).padStart(2, '0')
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
  const hh = String(d.getUTCHours()).padStart(2, '0')
  const mi = String(d.getUTCMinutes()).padStart(2, '0')
  return `${dd}.${mm}. ${hh}:${mi}`
}

const REGION_NAMES = new Intl.DisplayNames(['de'], { type: 'region' })

/** "Deutschland" for "DE"; the code itself when it is not an ISO-3166 alpha-2 code. */
export function countryName(code: string | null): string {
  if (!code) return 'Unbekannt'
  return /^[A-Z]{2}$/.test(code) ? (REGION_NAMES.of(code) ?? code) : code
}
