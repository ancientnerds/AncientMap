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
 * 'vector-layers' like the layer download).
 *
 * A file counts as present where its loader finds it offline: labels.json and
 * the tiers wherever OfflineFetch reads (every app cache and the service
 * worker's precache, which holds the running build's start tiers:
 * pwa/globeStartPrecache.ts), the gray only in 'basemaps'. So a layer rebuild,
 * which renames the tiers, does not make the Download Manager report them
 * missing: the new worker precached them. A download fetches only the files
 * that are missing.
 */

import { GLOBE_LAYER_KEYS, getGlobeLayerUrl } from '../config/vectorLayers'
import { BASEMAP_CACHE, VECTOR_LAYER_CACHE } from '../pwa/cacheNames'
import { LABELS_FILE, grayBasemapFiles } from './BasemapCache'
import { OfflineFetch } from './OfflineFetch'

export interface StartFile {
  url: string
  size: number
  /** Where a download stores it. */
  cache: string
  /** Its loader goes through OfflineFetch (every app cache and the precache); else it reads only `cache`. */
  viaOfflineFetch: boolean
}

// Gzip-free byte sizes of the start tiers of the current manifest (2026-09-24),
// for the size estimate and the progress bar only.
const START_LAYER_BYTES: Record<(typeof GLOBE_LAYER_KEYS)[number], number> = {
  coastlines: 1_737_670,
  countryBorders: 399_406,
}

/** The coastline and border start tiers, the one list both exports below read. */
function startLayerFiles(): StartFile[] {
  return GLOBE_LAYER_KEYS.map(key => ({ url: getGlobeLayerUrl(key, 'start'), size: START_LAYER_BYTES[key], cache: VECTOR_LAYER_CACHE, viaOfflineFetch: true }))
}

/**
 * The coastline and border start tiers. They are in getLayerFiles too (the
 * 'complete' check of a layer download), but these files own them: a layer
 * download neither fetches nor clears them (VectorLayerCache).
 */
export function globeStartLayerUrls(): string[] {
  return startLayerFiles().map(file => file.url)
}

export function globeStartFiles(): StartFile[] {
  return [
    { ...LABELS_FILE, cache: BASEMAP_CACHE, viaOfflineFetch: true }, // geoLabelSystem / useGeoLabels: offlineFetch
    ...grayBasemapFiles().map(file => ({ ...file, cache: BASEMAP_CACHE, viaOfflineFetch: false })), // plain fetch, the worker's basemap rule
    ...startLayerFiles(),
  ]
}

export function startFilesSize(files: StartFile[]): number {
  return files.reduce((sum, file) => sum + file.size, 0)
}

async function isPresent(file: StartFile): Promise<boolean> {
  if (file.viaOfflineFetch) return OfflineFetch.isCached(file.url)
  return (await (await caches.open(file.cache)).match(file.url)) !== undefined
}

/** The start files an offline start would not find, in globeStartFiles order. */
export async function missingGlobeStartFiles(): Promise<StartFile[]> {
  const files = globeStartFiles()
  const present = await Promise.all(files.map(isPresent))
  return files.filter((_, i) => !present[i])
}

/** Fetches and stores `files` (missingGlobeStartFiles); a file that fails fails the download. */
export async function downloadGlobeStart(files: StartFile[], onProgress?: (loaded: number, total: number) => void): Promise<void> {
  const total = startFilesSize(files)
  let loaded = 0
  for (const file of files) {
    const response = await fetch(file.url)
    if (!response.ok) throw new Error(`Failed to download ${file.url}: HTTP ${response.status}`)
    await (await caches.open(file.cache)).put(file.url, response)
    loaded += file.size
    onProgress?.(loaded, total)
  }
}
