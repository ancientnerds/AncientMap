/** Pure text formatting shared by the blocks (tested in test/format.test.ts). */

/** Host of a URL without "www.". */
export function domainOf(url: string): string {
  return new URL(url).hostname.replace(/^www\./, '')
}

const EARTH_RADIUS_M = 6_371_008.8

/** Great-circle distance in metres. */
export function haversineM(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const rad = Math.PI / 180
  const dLat = (b.lat - a.lat) * rad
  const dLng = (b.lng - a.lng) * rad
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) ** 2
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(h))
}

/** "820 m", "1.4 km", "23 km". */
export function formatDistance(m: number): string {
  if (m < 1000) return `${Math.round(m / 10) * 10} m`
  if (m < 10_000) return `${(m / 1000).toFixed(1)} km`
  return `${Math.round(m / 1000)} km`
}

/** "3000 BCE" / "120 CE"; year 0 does not exist in the calendar. */
export function formatYear(year: number): string {
  if (year === 0) throw new Error('year 0 does not exist; use -1 (1 BCE) or 1 (1 CE)')
  return year < 0 ? `${-year} BCE` : `${year} CE`
}

/** About six round ticks between from and to, never year 0. */
export function yearTicks(from: number, to: number): number[] {
  const raw = (to - from) / 6
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw) as number
  const ticks: number[] = []
  for (let y = Math.ceil(from / step) * step; y <= to; y += step) if (y !== 0) ticks.push(y)
  return ticks
}

/** The house probability language of the papers (brief section 4) for a share in percent. */
export function verbal(p: number): string {
  if (p >= 90) return 'almost certain'
  if (p >= 75) return 'very likely'
  if (p >= 60) return 'likely'
  if (p > 40) return 'roughly even'
  if (p > 25) return 'unlikely'
  return 'very unlikely'
}

/** A number with thousands separators and at most `decimals` decimals ("1,650", "12.5"). */
export function formatNumber(value: number, decimals = 1): string {
  return value.toLocaleString('en-US', { maximumFractionDigits: decimals })
}
