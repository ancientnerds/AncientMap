/**
 * EmpireCache - Handles caching of historical empire boundary GeoJSON files
 * Uses Service Worker cache for GeoJSON data
 */

import { EMPIRES, type EmpireConfig } from '../config/empireData'
import { OfflineStorage } from './OfflineStorage'

const CACHE_NAME = 'historical-data'
const HISTORICAL_BASE_PATH = '/data/historical'

class EmpireCacheClass {
  /**
   * Get list of available empires
   */
  getAvailableEmpires(): EmpireConfig[] {
    return EMPIRES
  }

  /**
   * Get empires grouped by region
   */
  getEmpiresByRegion(): Record<string, EmpireConfig[]> {
    const grouped: Record<string, EmpireConfig[]> = {}
    for (const empire of EMPIRES) {
      if (!grouped[empire.region]) {
        grouped[empire.region] = []
      }
      grouped[empire.region].push(empire)
    }
    return grouped
  }

  /**
   * Get info for a specific empire
   */
  getEmpireInfo(empireId: string): EmpireConfig | undefined {
    return EMPIRES.find(e => e.id === empireId)
  }

  /**
   * Get available years for an empire by fetching its index
   */
  async getAvailableYears(empireId: string): Promise<number[]> {
    try {
      const response = await fetch(`${HISTORICAL_BASE_PATH}/${empireId}/index.json`)
      if (response.ok) {
        const index = await response.json()
        return index.years || []
      }
    } catch {
      // Fall through
    }

    // Try metadata.json as fallback
    try {
      const response = await fetch(`${HISTORICAL_BASE_PATH}/${empireId}/metadata.json`)
      if (response.ok) {
        const metadata = await response.json()
        return metadata.years || []
      }
    } catch {
      // No data available
    }

    return []
  }

  /**
   * Download and cache all data for an empire
   */
  async downloadEmpire(
    empireId: string,
    onProgress?: (loaded: number, total: number) => void
  ): Promise<void> {
    const empire = this.getEmpireInfo(empireId)
    if (!empire) throw new Error(`Unknown empire: ${empireId}`)

    const cache = await caches.open(CACHE_NAME)
    let loadedBytes = 0

    const years = await this.getAvailableYears(empireId)
    const total = years.length * 10 * 1024 // Rough estimate

    for (const year of years) {
      const url = `${HISTORICAL_BASE_PATH}/${empireId}/${year}.geojson`
      try {
        const fileResponse = await fetch(url)
        if (fileResponse.ok) {
          const clone = fileResponse.clone()
          const blob = await fileResponse.blob()
          loadedBytes += blob.size
          await cache.put(url, clone)
          onProgress?.(Math.min(loadedBytes, total), total)
        }
      } catch (e) {
        console.warn(`Failed to cache empire file: ${url}`)
      }
    }

    await OfflineStorage.addDownloadedEmpire(empireId)
  }

  /**
   * Check if an empire is cached
   */
  async isEmpireCached(empireId: string): Promise<boolean> {
    const state = await OfflineStorage.getDownloadState()
    return state.empires.includes(empireId)
  }

  /**
   * Get list of cached empire IDs
   */
  async getCachedEmpires(): Promise<string[]> {
    const state = await OfflineStorage.getDownloadState()
    return state.empires
  }

  /**
   * Remove cached empire data
   */
  async clearEmpire(empireId: string): Promise<void> {
    const cache = await caches.open(CACHE_NAME)
    const years = await this.getAvailableYears(empireId)

    for (const year of years) {
      const url = `${HISTORICAL_BASE_PATH}/${empireId}/${year}.geojson`
      await cache.delete(url)
    }

    await OfflineStorage.removeDownloadedEmpire(empireId)
  }

  /**
   * Clear all cached empire data
   */
  async clearAllEmpires(): Promise<void> {
    const cachedEmpires = await this.getCachedEmpires()
    for (const empireId of cachedEmpires) {
      await this.clearEmpire(empireId)
    }
  }

  /**
   * Estimate size for an empire download (rough estimate: ~10KB per year file)
   */
  estimateEmpireSize(_empireId: string): number {
    return 100 * 1024 // 100KB rough estimate per empire
  }

  /**
   * Estimate total size for multiple empires
   */
  estimateSize(empireIds: string[]): number {
    return empireIds.reduce((total, id) => total + this.estimateEmpireSize(id), 0)
  }

  /**
   * Get total size of all empires (rough estimate)
   */
  getTotalSize(): number {
    return EMPIRES.length * 100 * 1024
  }
}

export const EmpireCache = new EmpireCacheClass()
