/**
 * BasemapCache - Handles caching of satellite basemap imagery
 * Uses Service Worker cache for large image files. The gray basemap and
 * labels.json, which the globe's start cannot do without, come with every
 * offline download (GlobeStartCache); there is no separate 'Labels' item.
 */

import { OfflineStorage } from './OfflineStorage'
import { BASEMAP_CACHE } from '../pwa/cacheNames'
import { BASEMAP_TIERS, getBasemapAssets, getBasemapTier, tierRank, type BasemapTier } from '../utils/deviceTier'

export type BasemapType = 'satellite'

interface BasemapItemInfo {
  id: BasemapType
  name: string
  files: { url: string; size: number }[]
  totalSize: number
}

// Byte sizes of the basemap files (public/data/basemaps, content-stable).
const BASEMAP_BYTES: Record<BasemapTier, { gray: number; satellite: number }> = {
  low: { gray: 109_724, satellite: 714_326 },
  med: { gray: 482_678, satellite: 2_657_496 },
  high: { gray: 3_301_588, satellite: 17_001_226 },
}

/**
 * A basemap kind at every tier up to the device's maximum: what the globe's
 * loader can request on this device. The start tier follows the window height
 * at load time, so all of them. The GPU limit is unknown here (0 = the largest
 * the device class allows); the service worker's basemap rule serves these
 * entries from the same 'basemaps' cache under the same URLs.
 */
function tierFiles(kind: 'gray' | 'satellite'): { url: string; size: number }[] {
  const max = getBasemapTier(0)
  return BASEMAP_TIERS.filter(tier => tierRank(tier) <= tierRank(max))
    .map(tier => ({ url: getBasemapAssets(tier)[kind], size: BASEMAP_BYTES[tier][kind] }))
}

/** The gray: critical at the start tier, so every offline download stores it (GlobeStartCache). */
export function grayBasemapFiles(): { url: string; size: number }[] {
  return tierFiles('gray')
}

/** Labels data file (critical for the start too: GlobeStartCache stores it with every download). */
export const LABELS_FILE = { url: '/data/labels.json', size: 1_087_841 }

function item(id: BasemapType, name: string, files: { url: string; size: number }[]): BasemapItemInfo {
  return { id, name, files, totalSize: files.reduce((sum, f) => sum + f.size, 0) }
}

/** Built on use: the satellite item depends on the device (window/navigator, never at module scope). */
function basemapItems(): Record<BasemapType, BasemapItemInfo> {
  return {
    satellite: item('satellite', 'Satellite', tierFiles('satellite')),
  }
}


class BasemapCacheClass {
  /**
   * Get list of available basemap items (Satellite)
   */
  getBasemapItems(): BasemapItemInfo[] {
    return Object.values(basemapItems())
  }

  /**
   * Get info for a specific basemap item
   */
  getBasemapItemInfo(id: BasemapType): BasemapItemInfo {
    return basemapItems()[id]
  }

  /**
   * Download and cache a basemap item (all files for that item)
   */
  async downloadBasemapItem(
    id: BasemapType,
    onProgress?: (loaded: number, total: number) => void
  ): Promise<void> {
    const item = basemapItems()[id]
    const cache = await caches.open(BASEMAP_CACHE)
    let totalLoaded = 0
    const totalSize = item.totalSize

    for (const file of item.files) {
      const response = await fetch(file.url)
      if (!response.ok) {
        throw new Error(`Failed to download ${file.url}: ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('ReadableStream not supported')
      }

      const chunks: Uint8Array[] = []
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        chunks.push(value)
        totalLoaded += value.length
        onProgress?.(totalLoaded, totalSize)
      }

      // Combine chunks and cache
      const contentType = file.url.endsWith('.json') ? 'application/json' :
                          file.url.endsWith('.webp') ? 'image/webp' :
                          file.url.endsWith('.png') ? 'image/png' : 'image/jpeg'
      const blob = new Blob(chunks as BlobPart[], { type: contentType })
      await cache.put(file.url, new Response(blob, {
        headers: {
          'Content-Type': contentType,
          'Content-Length': String(blob.size)
        }
      }))
    }

    // Update offline storage state
    await OfflineStorage.addBasemapItem(id)
  }

  /**
   * Check if a basemap item is cached (see getCachedItems)
   */
  async isBasemapItemCached(id: BasemapType): Promise<boolean> {
    return (await this.getCachedItems()).includes(id)
  }

  /**
   * The basemap items whose offline download is complete: marked downloaded,
   * and every file in the 'basemaps' cache. A 'Satellite' download from before
   * the basemap tiers holds satellite_high.webp only, so it is not complete and
   * the Download Manager offers it again (VectorLayerCache.getCachedLayers does
   * the same for the layers). The mark of a 'Labels' download from before the
   * start files names no item any more: labels.json is a start file now.
   */
  async getCachedItems(): Promise<BasemapType[]> {
    const state = await OfflineStorage.getDownloadState()
    const items = basemapItems()
    const marked = (state.basemapItems || []).filter((id): id is BasemapType => id in items)
    const cache = await caches.open(BASEMAP_CACHE)
    const complete = await Promise.all(marked.map(async id => {
      const hits = await Promise.all(items[id].files.map(file => cache.match(file.url)))
      return hits.every(Boolean)
    }))
    return marked.filter((_, i) => complete[i])
  }

  /**
   * Remove a specific basemap item from cache
   */
  async clearBasemapItem(id: BasemapType): Promise<void> {
    const item = basemapItems()[id]
    const cache = await caches.open(BASEMAP_CACHE)

    for (const file of item.files) {
      await cache.delete(file.url)
    }

    await OfflineStorage.removeBasemapItem(id)
  }

  /**
   * Remove all cached basemaps
   */
  async clearAll(): Promise<void> {
    await caches.delete(BASEMAP_CACHE)
    const state = await OfflineStorage.getDownloadState()
    state.basemapItems = []
    state.basemapQualities = [] // Legacy cleanup
    state.basemapQuality = 'none'
    await OfflineStorage.setMetadata('download-state', state)
  }

  /**
   * Estimate total size for selected items
   */
  estimateSize(ids: BasemapType[]): number {
    const items = basemapItems()
    return ids.reduce((total, id) => total + items[id].totalSize, 0)
  }

  // Legacy compatibility methods
  getBasemapOptions() {
    return this.getBasemapItems()
  }

  async getCachedQualities(): Promise<string[]> {
    return this.getCachedItems()
  }
}

export const BasemapCache = new BasemapCacheClass()
