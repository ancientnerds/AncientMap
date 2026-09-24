/**
 * VectorLayerCache - Handles caching of vector layer GeoJSON files
 * Uses Service Worker cache for GeoJSON data
 */

import { OfflineFetch } from './OfflineFetch'
import { OfflineStorage } from './OfflineStorage'
import { LAYER_CONFIG, getLayerFiles, type VectorLayerKey } from '../config/vectorLayers'

export interface VectorLayerInfo {
  id: string
  name: string
  color: string
  fileCount: number
  estimatedSize: number
}

// 157 sea levels (-150 to 6) - only highest resolution needed
const PALEOSHORELINE_FILE_COUNT = 157

function isVectorLayerKey(id: string): id is VectorLayerKey {
  return id in LAYER_CONFIG
}

/** A globe vector layer: the files are exactly what the globe fetches (getLayerFiles). */
function globeLayer(id: VectorLayerKey, name: string, color: string, estimatedSize: number): VectorLayerInfo {
  return { id, name, color, fileCount: getLayerFiles(id).length, estimatedSize }
}

// Sizes are the sums of the files getLayerFiles lists (measured 2026-09-23).
const VECTOR_LAYERS: VectorLayerInfo[] = [
  globeLayer('coastlines', 'Coastlines', '#00e0d0', 36.6 * 1024 * 1024),   // start 1.7 + detail 9.8 + hires 25.0 MB
  globeLayer('countryBorders', 'Country Borders', '#00e0d0', 1.8 * 1024 * 1024),  // start 0.4 + detail 1.4 MB
  globeLayer('rivers', 'Rivers', '#2196f3', 8.2 * 1024 * 1024),    // Natural Earth 110m, 50m, 10m
  globeLayer('lakes', 'Lakes', '#1976d2', 6.0 * 1024 * 1024),      // Natural Earth 110m, 50m, 10m
  globeLayer('coralReefs', 'Coral Reefs', '#ff6b9d', 42.6 * 1024 * 1024),  // 110m, 50m, 10m + labels
  globeLayer('glaciers', 'Glaciers', '#88ddff', 8.3 * 1024 * 1024),  // 110m, 50m, 10m + labels
  {
    id: 'paleoshorelines',
    name: 'Paleoshorelines',
    color: '#C2B280',
    fileCount: PALEOSHORELINE_FILE_COUNT,  // 157 sea levels
    estimatedSize: 2.3 * 1024 * 1024 * 1024,  // ~2.3 GB (50m resolution)
  },
  globeLayer('plateBoundaries', 'Plate Boundaries', '#FF6B6B', 0.24 * 1024 * 1024),  // boundaries + labels
]

// Generate all sea levels from -150 to 6
const SEA_LEVELS: number[] = []
for (let i = -150; i <= 6; i++) {
  SEA_LEVELS.push(i)
}

const CACHE_NAME = 'vector-layers'

class VectorLayerCacheClass {
  /**
   * Get list of available vector layers
   */
  getAvailableLayers(): VectorLayerInfo[] {
    return VECTOR_LAYERS
  }

  /**
   * Get info for a specific layer
   */
  getLayerInfo(layerId: string): VectorLayerInfo | undefined {
    return VECTOR_LAYERS.find(l => l.id === layerId)
  }

  /**
   * Get all sea levels
   */
  getSeaLevels(): number[] {
    return SEA_LEVELS
  }

  /**
   * Download and cache a vector layer
   */
  async downloadLayer(
    layerId: string,
    onProgress?: (loaded: number, total: number) => void
  ): Promise<void> {
    const layer = this.getLayerInfo(layerId)
    if (!layer) throw new Error(`Unknown layer: ${layerId}`)

    const cache = await caches.open(CACHE_NAME)
    const total = layer.estimatedSize
    let loadedBytes = 0

    if (layerId === 'paleoshorelines') {
      // Download paleoshorelines - 157 sea levels, medium resolution (50m)
      const totalFiles = SEA_LEVELS.length
      let filesDownloaded = 0

      for (const level of SEA_LEVELS) {
        const url = `/data/sea-levels/${level}m/contour_50m.json`
        try {
          const response = await fetch(url)
          if (response.ok) {
            // Get size from Content-Length header, or estimate
            const contentLength = response.headers.get('Content-Length')
            const fileSize = contentLength ? parseInt(contentLength, 10) : (total / totalFiles)

            // Cache the response directly
            await cache.put(url, response)

            loadedBytes += fileSize
            filesDownloaded++
          }
        } catch (e) {
          console.warn(`Failed to cache paleoshoreline: ${url}`)
          filesDownloaded++
        }

        // Update progress after each file
        onProgress?.(Math.min(loadedBytes, total), total)

        // Small yield every 30 files to prevent UI freeze
        if (filesDownloaded % 30 === 0) {
          await new Promise(r => setTimeout(r, 10))
        }
      }
    } else {
      if (!isVectorLayerKey(layerId)) throw new Error(`Unknown layer: ${layerId}`)
      // Exactly the URLs the globe fetches, so OfflineFetch's exact-URL match finds them.
      // A file that fails fails the download: the layer is not marked downloaded.
      const files = getLayerFiles(layerId)
      for (const url of files) {
        const response = await fetch(url)
        if (!response.ok) throw new Error(`Failed to download ${url}: HTTP ${response.status}`)
        // Get size from Content-Length header, or estimate
        const contentLength = response.headers.get('Content-Length')
        const fileSize = contentLength ? parseInt(contentLength, 10) : (total / files.length)
        await cache.put(url, response)
        loadedBytes += fileSize
        onProgress?.(Math.min(loadedBytes, total), total)
      }
    }

    // Update offline storage state
    await OfflineStorage.addDownloadedLayer(layerId)
  }

  /**
   * The layers whose offline download is complete: marked downloaded, and for a globe layer
   * every file of getLayerFiles in the cache where offline mode reads it (OfflineFetch, exact
   * URL). A download from before the coastline/border tiers holds coast_hires only, so it is
   * not complete and the Download Manager offers the download again. Paleoshorelines are no
   * globe layer files; they keep their download mark.
   */
  async getCachedLayers(): Promise<string[]> {
    const state = await OfflineStorage.getDownloadState()
    const marked = state.layers || []
    const complete = await Promise.all(marked.map(async id => {
      if (!isVectorLayerKey(id)) return id === 'paleoshorelines'
      const cached = await Promise.all(getLayerFiles(id).map(url => OfflineFetch.isCached(url)))
      return cached.every(Boolean)
    }))
    return marked.filter((_, i) => complete[i])
  }

  /**
   * Remove cached layer data
   */
  async clearLayer(layerId: string): Promise<void> {
    const layer = this.getLayerInfo(layerId)
    if (!layer) return

    const cache = await caches.open(CACHE_NAME)

    if (layerId === 'paleoshorelines') {
      // Clear paleoshoreline files (50m resolution)
      for (const level of SEA_LEVELS) {
        const url = `/data/sea-levels/${level}m/contour_50m.json`
        await cache.delete(url)
      }
    } else {
      if (!isVectorLayerKey(layerId)) throw new Error(`Unknown layer: ${layerId}`)
      for (const url of getLayerFiles(layerId)) {
        await cache.delete(url)
      }
    }

    await OfflineStorage.removeDownloadedLayer(layerId)
  }

  /**
   * Clear all cached layer data
   */
  async clearAllLayers(): Promise<void> {
    await caches.delete(CACHE_NAME)
    const state = await OfflineStorage.getDownloadState()
    state.layers = []
    await OfflineStorage.setMetadata('download-state', state)
  }

  /**
   * Estimate total size for selected layers
   */
  estimateSize(layerIds: string[]): number {
    return layerIds.reduce((total, id) => {
      const layer = this.getLayerInfo(id)
      return total + (layer?.estimatedSize || 0)
    }, 0)
  }
}

export const VectorLayerCache = new VectorLayerCacheClass()
