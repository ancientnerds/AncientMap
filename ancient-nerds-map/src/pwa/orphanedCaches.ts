/**
 * Cache Storage that an earlier service worker or build filled and nothing
 * reads any more. The old rule for GitHub-hosted Natural Earth files cached
 * into `natural-earth`, and old Download Manager runs put the same GitHub URLs
 * into `vector-layers`; the globe's layers are self-hosted now
 * (src/config/vectorLayers.ts), so both only take up the visitor's storage.
 * The coastline and border tiers carry a content hash in their names
 * (scripts/build_globe_layers.py): after a layer rebuild the copies of the
 * earlier names stay in `vector-layers`, since an offline download stores them
 * with a plain cache.put that the runtime rule's expiration never sees and
 * clearing a layer deletes only the running build's names. The build removes
 * those files from the server, so no request can refresh them either; every
 * tier the running build does not name is dropped. The globe's `sw` background
 * task removes all of them once the worker is registered
 * (registerServiceWorker.ts: serviceWorkerTask).
 *
 * No browser access at module scope (SSR import safety): the caller passes
 * the CacheStorage.
 */

import { GLOBE_LAYER_KEYS, getGlobeLayerUrl } from '../config/vectorLayers'
import { VECTOR_LAYER_CACHE } from './cacheNames'

/** The cache of the removed runtime rule for raw.githubusercontent.com. */
const NATURAL_EARTH_CACHE = 'natural-earth'
/** Where the layers came from before they were self-hosted. */
const ORPHANED_LAYER_HOST = 'raw.githubusercontent.com'
/** The directory of the content-hashed coastline and border tiers (build_globe_layers.py URL_PREFIX). */
const GLOBE_TIER_DIR = '/data/layers/globe/'

/** A `vector-layers` entry nothing reads: a GitHub layer, or a globe tier of an earlier layer build. */
function isOrphaned(url: URL, currentTiers: Set<string>): boolean {
  if (url.host === ORPHANED_LAYER_HOST) return true
  return url.pathname.startsWith(GLOBE_TIER_DIR) && !currentTiers.has(url.pathname)
}

export async function pruneOrphanedCaches(storage: CacheStorage): Promise<void> {
  await storage.delete(NATURAL_EARTH_CACHE)
  // open() would create the cache: only look where there is one
  if (!(await storage.has(VECTOR_LAYER_CACHE))) return
  const currentTiers = new Set(GLOBE_LAYER_KEYS.flatMap(key => [getGlobeLayerUrl(key, 'start'), getGlobeLayerUrl(key, 'detail')]))
  const cache = await storage.open(VECTOR_LAYER_CACHE)
  const orphaned = (await cache.keys()).filter(request => isOrphaned(new URL(request.url), currentTiers))
  await Promise.all(orphaned.map(request => cache.delete(request)))
}
