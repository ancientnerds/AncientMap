/**
 * VectorLayerCache - Handles caching of vector layer GeoJSON files
 * Uses Service Worker cache for GeoJSON data
 */

import { OfflineStorage } from './OfflineStorage'

export interface VectorLayerInfo {
  id: string
  name: string
  color: string
  fileCount: number
  estimatedSize: number
  detailLevels: string[]
}

// 157 sea levels (-150 to 6) - only highest resolution needed
const PALEOSHORELINE_FILE_COUNT = 157

// Layer definitions
const VECTOR_LAYERS: VectorLayerInfo[] = [
  {
    id: 'coastlines',
    name: 'Coastlines',
    color: '#00e0d0',
    fileCount: 1,  // Only hires
    estimatedSize: 15 * 1024 * 1024,
    detailLevels: ['hires']
  },
  {
    id: 'countryBorders',
    name: 'Country Borders',
    color: '#00e0d0',
    fileCount: 1,  // Only 10m from Natural Earth
    estimatedSize: 5 * 1024 * 1024,
    detailLevels: ['10m']
  },
  {
    id: 'rivers',
    name: 'Rivers',
    color: '#2196f3',
    fileCount: 3,  // LOD: 110m, 50m, 10m
    estimatedSize: 30 * 1024 * 1024,
    detailLevels: ['10m', '50m', '110m']
  },
  {
    id: 'lakes',
    name: 'Lakes',
    color: '#1976d2',
    fileCount: 3,  // LOD: 110m, 50m, 10m
    estimatedSize: 20 * 1024 * 1024,
    detailLevels: ['10m', '50m', '110m']
  },
  {
    id: 'coralReefs',
    name: 'Coral Reefs',
    color: '#ff6b9d',
    fileCount: 1,  // Only hires
    estimatedSize: 5 * 1024 * 1024,
    detailLevels: ['hires']
  },
  {
    id: 'glaciers',
    name: 'Glaciers',
    color: '#88ddff',
    fileCount: 1,  // Only hires
    estimatedSize: 10 * 1024 * 1024,
    detailLevels: ['hires']
  },
  {
    id: 'paleoshorelines',
    name: 'Paleoshorelines',
    color: '#C2B280',
    fileCount: PALEOSHORELINE_FILE_COUNT,  // 157 sea levels
    estimatedSize: 2.3 * 1024 * 1024 * 1024,  // ~2.3 GB (50m resolution)
    detailLevels: ['50m']
  },
  {
    id: 'plateBoundaries',
    name: 'Plate Boundaries',
    color: '#FF6B6B',
    fileCount: 1,  // Single file
    estimatedSize: 2 * 1024 * 1024,  // ~2 MB
    detailLevels: ['hires']
  },
]

// File mappings - local files use 'local' category, Natural Earth use 'natural-earth'
const FILE_MAPPINGS: Record<string, { path: string; category: 'local' | 'natural-earth' }> = {
  coastlines: { path: 'coast_hires', category: 'local' },
  countryBorders: { path: 'admin_0_boundary_lines_land', category: 'natural-earth' },
  rivers: { path: 'rivers_lake_centerlines', category: 'natural-earth' },
  lakes: { path: 'lakes', category: 'natural-earth' },
  coralReefs: { path: 'coral_reefs_hires', category: 'local' },
  glaciers: { path: 'glaciers_hires', category: 'local' },
  plateBoundaries: { path: 'plate_boundaries_hires', category: 'local' },
}

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
   * Get URL for a layer file at a specific detail level
   */
  private getLayerUrl(layerId: string, detail: string): string {
    const mapping = FILE_MAPPINGS[layerId]
    if (!mapping) throw new Error(`Unknown layer: ${layerId}`)

    if (mapping.category === 'natural-earth') {
      // Natural Earth layers use external GitHub URLs with LOD
      return `https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_${detail}_${mapping.path}.geojson`
    } else {
      // Local hires layers
      return `/data/layers/${mapping.path}.geojson`
    }
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
      // Download layer at all detail levels (1 for hires, 3 for LOD layers)
      for (const detail of layer.detailLevels) {
        const url = this.getLayerUrl(layerId, detail)
        try {
          const response = await fetch(url)
          if (response.ok) {
            // Get size from Content-Length header, or estimate
            const contentLength = response.headers.get('Content-Length')
            const fileSize = contentLength ? parseInt(contentLength, 10) : (total / layer.detailLevels.length)

            // Cache the response directly
            await cache.put(url, response)

            loadedBytes += fileSize
          }
        } catch (e) {
          console.warn(`Failed to cache layer: ${url}`)
        }
        onProgress?.(Math.min(loadedBytes, total), total)
      }
    }

    // Update offline storage state
    await OfflineStorage.addDownloadedLayer(layerId)
  }

  /**
   * Check if a layer is cached
   */
  async isLayerCached(layerId: string): Promise<boolean> {
    const state = await OfflineStorage.getDownloadState()
    return state.layers?.includes(layerId) ?? false
  }

  /**
   * Get list of cached layer IDs
   */
  async getCachedLayers(): Promise<string[]> {
    const state = await OfflineStorage.getDownloadState()
    return state.layers || []
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
      for (const detail of layer.detailLevels) {
        const url = this.getLayerUrl(layerId, detail)
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
