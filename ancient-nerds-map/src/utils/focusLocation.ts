/**
 * The focus site's position for a ?focus= link: the intro warp lands on it,
 * and the loading overlay waits for this lookup (App's focusResolved). Like the
 * IP lookup it gets a deadline, so an API that does not answer cannot hold the
 * overlay. A failure, a timeout or a site without a position is logged and
 * answers null: the intro then aims at the IP location or the default target,
 * as a failed lookup always did. Aborting the caller's signal rejects with its
 * reason.
 *
 * Module scope touches no browser global (SSR-safe import).
 */

import { config } from '../config'
import { fetchJsonWithDeadline } from './fetchWithDeadline'
import { apiDetailToSiteData, type ApiSiteDetail } from './siteApi'

/** Below the service worker's 10 s NetworkFirst timeout for /api/sites/ (pwa/runtimeCaching.ts). */
export const FOCUS_LOOKUP_DEADLINE_MS = 8000

export async function lookupFocusLocation(siteId: string, signal: AbortSignal): Promise<[number, number] | null> {
  let detail: ApiSiteDetail
  try {
    detail = await fetchJsonWithDeadline(`${config.api.baseUrl}/sites/${siteId}`, signal, FOCUS_LOOKUP_DEADLINE_MS) as ApiSiteDetail
  } catch (err) {
    if (signal.aborted) throw signal.reason
    console.warn(`[globe] focus site ${siteId}: position lookup failed`, err)
    return null
  }
  const [lng, lat] = apiDetailToSiteData(detail).coordinates
  if (Number.isNaN(lng) || Number.isNaN(lat)) {
    console.warn(`[globe] focus site ${siteId} has no position`)
    return null
  }
  return [lng, lat]
}
