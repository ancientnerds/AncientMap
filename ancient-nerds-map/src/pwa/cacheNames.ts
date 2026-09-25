/**
 * Cache Storage names shared by the service worker's rules (runtimeCaching.ts,
 * imported by vite.config.ts), the offline downloads and OfflineFetch, and the
 * cleanup of caches earlier workers left behind (orphanedCaches.ts). Pure data.
 */

/** Coastlines, borders, rivers, lakes and the other vector layers. */
export const VECTOR_LAYER_CACHE = 'vector-layers'

/** The basemap images (the service worker's basemap rule and the offline download) and labels.json. */
export const BASEMAP_CACHE = 'basemaps'

/**
 * workbox's precache (globe.html, the JS, the fonts, the globe's start tiers:
 * globeStartPrecache.ts) for the worker registered at scope '/' of `origin`:
 * `workbox-precache-v2-<scope>` (workbox-core _private/cacheNames.js).
 */
export function precacheCacheName(origin: string): string {
  return `workbox-precache-v2-${origin}/`
}
