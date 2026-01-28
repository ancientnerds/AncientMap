/**
 * BasemapCache - Handles caching of satellite basemap imagery and labels
 * Uses Service Worker cache for large image files
 */

import { OfflineStorage } from './OfflineStorage'

export type BasemapType = 'satellite' | 'labels'

interface BasemapItemInfo {
  id: BasemapType
  name: string
  files: { url: string; size: number }[]
  totalSize: number
}

// Satellite imagery - single high quality file
const SATELLITE_FILES = [
  { url: '/data/basemaps/satellite_high.webp', size: 17 * 1024 * 1024 }, // ~17 MB (WebP)
]

// Labels data file
const LABELS_FILES = [
  { url: '/data/labels.json', size: 1.1 * 1024 * 1024 },
]

const BASEMAP_ITEMS: Record<BasemapType, BasemapItemInfo> = {
  satellite: {
    id: 'satellite',
    name: 'Satellite',
    files: SATELLITE_FILES,
    totalSize: SATELLITE_FILES.reduce((sum, f) => sum + f.size, 0)
  },
  labels: {
    id: 'labels',
    name: 'Labels',
    files: LABELS_FILES,
    totalSize: LABELS_FILES.reduce((sum, f) => sum + f.size, 0)
  }
}

const CACHE_NAME = 'basemaps'

class BasemapCacheClass {
  /**
   * Get list of available basemap items (Satellite, Labels)
   */
  getBasemapItems(): BasemapItemInfo[] {
    return Object.values(BASEMAP_ITEMS)
  }

  /**
   * Get info for a specific basemap item
   */
  getBasemapItemInfo(id: BasemapType): BasemapItemInfo {
    return BASEMAP_ITEMS[id]
  }

  /**
   * Download and cache a basemap item (all files for that item)
   */
  async downloadBasemapItem(
    id: BasemapType,
    onProgress?: (loaded: number, total: number) => void
  ): Promise<void> {
    const item = BASEMAP_ITEMS[id]
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
    const item = BASEMAP_ITEMS[id]
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
    return ids.reduce((total, id) => total + BASEMAP_ITEMS[id].totalSize, 0)
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
