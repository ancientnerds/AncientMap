/**
 * The files the globe's start cannot do without offline: a failure of any of
 * them is the error screen (contract C0). labels.json, the gray basemap (at
 * every tier up to the device's maximum: the start tier follows the window at
 * load time) and the coastline and border start tiers. Every offline download
 * stores them, whatever the visitor ticked (DownloadManager), so an offline
 * start works with any download, not only with the optional 'Satellite' item.
 *
 * Each file goes into the cache its loader reads offline: the gray is fetched
 * through the service worker's basemap rule ('basemaps'), labels.json and the
 * layer tiers through OfflineFetch (labels.json in 'basemaps', the tiers in
 * 'vector-layers' like the layer download and the service worker's globe
 * layer rule).
 */

import { GLOBE_LAYER_KEYS, getGlobeLayerUrl } from '../config/vectorLayers'
import { BASEMAP_CACHE, VECTOR_LAYER_CACHE } from '../pwa/cacheNames'
import { LABELS_FILE, grayBasemapFiles } from './BasemapCache'

interface StartFile { url: string; size: number; cache: string }

// Gzip-free byte sizes of the start tiers of the current manifest (2026-09-24),
// for the size estimate and the progress bar only.
const START_LAYER_BYTES: Record<(typeof GLOBE_LAYER_KEYS)[number], number> = {
  coastlines: 1_737_670,
  countryBorders: 399_406,
}

export function globeStartFiles(): StartFile[] {
  return [
    { ...LABELS_FILE, cache: BASEMAP_CACHE },
    ...grayBasemapFiles().map(file => ({ ...file, cache: BASEMAP_CACHE })),
    ...GLOBE_LAYER_KEYS.map(key => ({ url: getGlobeLayerUrl(key, 'start'), size: START_LAYER_BYTES[key], cache: VECTOR_LAYER_CACHE })),
  ]
}

export function globeStartSize(): number {
  return globeStartFiles().reduce((sum, file) => sum + file.size, 0)
}

/** Every start file is in the cache its loader reads. */
export async function isGlobeStartCached(): Promise<boolean> {
  const hits = await Promise.all(globeStartFiles().map(async file => (await caches.open(file.cache)).match(file.url)))
  return hits.every(Boolean)
}

/** Fetches and stores every start file; a file that fails fails the download. */
export async function downloadGlobeStart(onProgress?: (loaded: number, total: number) => void): Promise<void> {
  const total = globeStartSize()
  let loaded = 0
  for (const file of globeStartFiles()) {
    const response = await fetch(file.url)
    if (!response.ok) throw new Error(`Failed to download ${file.url}: HTTP ${response.status}`)
    await (await caches.open(file.cache)).put(file.url, response)
    loaded += file.size
    onProgress?.(loaded, total)
  }
}
