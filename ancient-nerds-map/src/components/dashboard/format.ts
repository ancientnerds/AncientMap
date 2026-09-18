/** Number and time formatting shared by the dashboard panels. English locale,
 *  UTC hours — the founders compare against Umami, which shows UTC too. */

export function fmtInt(n: number): string {
  return n.toLocaleString('en-GB')
}

/** Share of `part` in `whole` as "37 %"; "0 %" when there is nothing to divide by. */
export function fmtShare(part: number, whole: number): string {
  return `${whole ? Math.round((part / whole) * 100) : 0} %`
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "14:00" for a UTC hour of the day. */
export function fmtHour(hour: number): string {
  return `${String(hour).padStart(2, '0')}:00`
}

/** "17 Sep 14:05" in UTC. */
export function fmtStamp(iso: string): string {
  const d = new Date(iso)
  const dd = String(d.getUTCDate()).padStart(2, '0')
  const hh = String(d.getUTCHours()).padStart(2, '0')
  const mi = String(d.getUTCMinutes()).padStart(2, '0')
  return `${dd} ${MONTHS[d.getUTCMonth()]} ${hh}:${mi}`
}

/** "17 Sep 14:00" in UTC — a stamp without the minutes, for axis labels. */
export function fmtDayHour(d: Date): string {
  const dd = String(d.getUTCDate()).padStart(2, '0')
  const hh = String(d.getUTCHours()).padStart(2, '0')
  return `${dd} ${MONTHS[d.getUTCMonth()]} ${hh}:00`
}

const REGION_NAMES = new Intl.DisplayNames(['en'], { type: 'region' })

/** "Germany" for "DE"; the code itself when it is not an ISO-3166 alpha-2 code. */
export function countryName(code: string | null): string {
  if (!code) return 'Unknown'
  return /^[A-Z]{2}$/.test(code) ? (REGION_NAMES.of(code) ?? code) : code
}
