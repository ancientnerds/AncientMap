/**
 * Cache Storage names shared by the service worker's rules (runtimeCaching.ts,
 * imported by vite.config.ts), the offline downloads and OfflineFetch, and the
 * cleanup of caches earlier workers left behind (orphanedCaches.ts). Pure data.
 */

/** Coastlines, borders, rivers, lakes and the other vector layers. */
export const VECTOR_LAYER_CACHE = 'vector-layers'

/** The basemap images (the service worker's basemap rule and the offline download) and labels.json. */
export const BASEMAP_CACHE = 'basemaps'
