/**
 * The coastline and border start tiers in the service worker's precache
 * (vite.config.ts: workbox additionalManifestEntries). Pure data, imported by
 * vite.config.ts and by its test.
 *
 * Their file names carry a content hash compiled into the bundle
 * (globeLayers.generated.json), and globe.html with its JS is served cache-first
 * from the precache. The first online visit after a deploy that rebuilt the
 * layers still runs the previous build's JS, which never asks for the new
 * tiers, while the new worker installs; the next start runs the new JS, and
 * offline no cache the page filled holds its tiers. The worker that serves that
 * JS precaches exactly the tiers it asks for, and OfflineFetch reads the
 * precache (precacheCacheName), so an offline start finds them.
 *
 * `revision: null`: the name is the hash, so the precache keys the plain URL
 * and fetches it again only when the name changes.
 */

import { GLOBE_LAYER_KEYS, getGlobeLayerUrl } from '../config/vectorLayers'

export const GLOBE_START_PRECACHE = GLOBE_LAYER_KEYS.map(key => ({ url: getGlobeLayerUrl(key, 'start'), revision: null }))
