/**
 * The visitor's approximate position from their IP address, used to aim the
 * globe's intro (and the proximity filter's "use my location"). The providers
 * are the two the disclaimer names (shared/disclaimerContent.ts): ipwho.is,
 * then geojs.io when the first gives nothing.
 *
 * Each provider gets IP_LOOKUP_DEADLINE_MS, body included: the lookup runs in
 * parallel with the globe's start and must never be what the start waits for.
 * A failed provider is logged; when both fail the answer is null and the
 * caller keeps its default. Aborting the caller's signal rejects with its
 * reason and asks no further provider.
 *
 * Module scope touches no browser global (SSR-safe import).
 */

import { fetchJsonWithDeadline } from './fetchWithDeadline'

export const IP_LOOKUP_DEADLINE_MS = 2000

type LngLat = [number, number]

interface Provider {
  name: string
  url: string
  /** Coordinates from the provider's JSON, or null when it has none. */
  read: (data: unknown) => LngLat | null
}

const PROVIDERS: readonly Provider[] = [
  {
    name: 'ipwho.is',
    url: 'https://ipwho.is/',
    read: data => {
      const d = data as { success?: unknown; latitude?: unknown; longitude?: unknown } | null
      return d?.success && typeof d.latitude === 'number' && typeof d.longitude === 'number'
        ? [d.longitude, d.latitude]
        : null
    },
  },
  {
    name: 'geojs.io',
    url: 'https://get.geojs.io/v1/ip/geo.json',
    read: data => {
      const d = data as { latitude?: unknown; longitude?: unknown } | null
      const lat = parseFloat(String(d?.latitude))
      const lng = parseFloat(String(d?.longitude))
      return Number.isNaN(lat) || Number.isNaN(lng) ? null : [lng, lat]
    },
  },
]

export async function lookupIpLocation(signal: AbortSignal): Promise<LngLat | null> {
  for (const provider of PROVIDERS) {
    if (signal.aborted) throw signal.reason
    try {
      const coords = provider.read(await fetchJsonWithDeadline(provider.url, signal, IP_LOOKUP_DEADLINE_MS))
      if (coords) return coords
      console.warn(`[ip location] ${provider.name} answered without coordinates`)
    } catch (err) {
      if (signal.aborted) throw signal.reason
      console.warn(`[ip location] ${provider.name} failed:`, err)
    }
  }
  return null
}
