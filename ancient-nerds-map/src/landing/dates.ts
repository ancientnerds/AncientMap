const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/**
 * "Sep 7" — read straight off the ISO string, never through `new Date()`.
 *
 * The payload's timestamps carry no zone ("2026-08-31T00:00:00"), and JS
 * parses those as LOCAL time: `new Date(iso).getUTCDate()` then shifts the
 * day by the renderer's offset — the SSR sidecar (UTC) would print
 * "Aug 30" where a browser in CEST prints "Aug 31", and hydration would
 * mismatch. Reading the fields verbatim is the only form that agrees byte
 * for byte everywhere — the same rule seo/display.ts::longDate follows.
 */
export function shortDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!m) throw new Error(`shortDate: not an ISO date: ${iso}`)
  return `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}`
}

/** "Aug 31 – Sep 6" for a journal week. */
export function dateRange(startIso: string | null, endIso: string | null): string {
  if (!startIso || !endIso) return ''
  return `${shortDate(startIso)} – ${shortDate(endIso)}`
}
