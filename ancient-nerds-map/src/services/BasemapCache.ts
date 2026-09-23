/**
 * BasemapCache - Handles caching of satellite basemap imagery and labels
 * Uses Service Worker cache for large image files
 */

import { OfflineStorage } from './OfflineStorage'
import { BASEMAP_TIERS, getBasemapAssets, getBasemapTier, tierRank, type BasemapTier } from '../utils/deviceTier'

export type BasemapType = 'satellite' | 'labels'

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
 * Basemap imagery for offline use: what the globe's loader requests on this
 * device - the gray (critical at the start tier) and the satellite, at every
 * tier up to the device's maximum. The start tier follows the window height
 * at load time, so all of them. The GPU limit is unknown here (0 = the
 * largest the device class allows); the service worker's basemap rule serves
 * these entries from the same 'basemaps' cache under the same URLs.
 */
function basemapFiles(): { url: string; size: number }[] {
  const max = getBasemapTier(0)
  return BASEMAP_TIERS.filter(tier => tierRank(tier) <= tierRank(max)).flatMap(tier => {
    const assets = getBasemapAssets(tier)
    return [
      { url: assets.gray, size: BASEMAP_BYTES[tier].gray },
      { url: assets.satellite, size: BASEMAP_BYTES[tier].satellite },
    ]
  })
}

// Labels data file
const LABELS_FILES = [
  { url: '/data/labels.json', size: 1.1 * 1024 * 1024 },
]

function item(id: BasemapType, name: string, files: { url: string; size: number }[]): BasemapItemInfo {
  return { id, name, files, totalSize: files.reduce((sum, f) => sum + f.size, 0) }
}

/** Built on use: the satellite item depends on the device (window/navigator, never at module scope). */
function basemapItems(): Record<BasemapType, BasemapItemInfo> {
  return {
    satellite: item('satellite', 'Satellite', basemapFiles()),
    labels: item('labels', 'Labels', LABELS_FILES),
  }
}

const CACHE_NAME = 'basemaps'

class BasemapCacheClass {
  /**
   * Get list of available basemap items (Satellite, Labels)
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
    const cache = await caches.open(CACHE_NAME)
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
   * Check if a basemap item is cached
   */
  async isBasemapItemCached(id: BasemapType): Promise<boolean> {
    const state = await OfflineStorage.getDownloadState()
    return state.basemapItems?.includes(id) ?? false
  }

  /**
   * Get list of cached basemap item IDs
   */
  async getCachedItems(): Promise<BasemapType[]> {
    const state = await OfflineStorage.getDownloadState()
    return (state.basemapItems || []) as BasemapType[]
  }

  /**
   * Remove a specific basemap item from cache
   */
  async clearBasemapItem(id: BasemapType): Promise<void> {
    const item = basemapItems()[id]
    const cache = await caches.open(CACHE_NAME)

    for (const file of item.files) {
      await cache.delete(file.url)
    }

    await OfflineStorage.removeBasemapItem(id)
  }

  /**
   * Remove all cached basemaps
   */
  async clearAll(): Promise<void> {
    await caches.delete(CACHE_NAME)
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
