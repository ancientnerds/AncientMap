import { shortDate } from '../seo/display'

/** "Aug 31 – Sep 6" for a journal week. */
export function dateRange(startIso: string | null, endIso: string | null): string {
  if (!startIso || !endIso) return ''
  return `${shortDate(startIso)} – ${shortDate(endIso)}`
}
