/**
 * Cache Storage that an earlier service worker filled and nothing reads any
 * more. The old rule for GitHub-hosted Natural Earth files cached into
 * `natural-earth`, and old Download Manager runs put the same GitHub URLs into
 * `vector-layers`; the globe's layers are self-hosted now
 * (src/config/vectorLayers.ts), so both only take up the visitor's storage.
 * The globe's `sw` background task removes them once the worker is registered
 * (registerServiceWorker.ts: serviceWorkerTask).
 *
 * No browser access at module scope (SSR import safety): the caller passes
 * the CacheStorage.
 */

import { VECTOR_LAYER_CACHE } from './cacheNames'

/** The cache of the removed runtime rule for raw.githubusercontent.com. */
const NATURAL_EARTH_CACHE = 'natural-earth'
/** Where the layers came from before they were self-hosted. */
const ORPHANED_LAYER_HOST = 'raw.githubusercontent.com'

export async function pruneOrphanedCaches(storage: CacheStorage): Promise<void> {
  await storage.delete(NATURAL_EARTH_CACHE)
  // open() would create the cache: only look where there is one
  if (!(await storage.has(VECTOR_LAYER_CACHE))) return
  const cache = await storage.open(VECTOR_LAYER_CACHE)
  const orphaned = (await cache.keys()).filter(request => new URL(request.url).host === ORPHANED_LAYER_HOST)
  await Promise.all(orphaned.map(request => cache.delete(request)))
}
