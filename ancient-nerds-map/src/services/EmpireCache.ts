/**
 * EmpireCache - Handles caching of historical empire boundary GeoJSON files
 * Uses Service Worker cache for GeoJSON data
 *
 * Scope: Civilizations that "touch ancient" (startYear before cutoff)
 * - Old World (Europe, Asia, Africa, Oceania): startYear <= 500 AD
 * - Americas: startYear <= 1500 AD
 */

import { OfflineStorage } from './OfflineStorage'

export interface EmpireInfo {
  id: string
  name: string
  region: string
  startYear: number
  endYear: number
  color: string
  fileCount: number      // Actual number of year files
  estimatedSize: number  // Actual size in bytes
}

// Empire definitions matching empireData.ts with accurate file counts/sizes
const EMPIRE_INFO: EmpireInfo[] = [
  // Ancient Near East (7)
  { id: 'egyptian', name: 'Egyptian Empire', region: 'Ancient Near East', startYear: -2401, endYear: -29, color: '#FFD700', fileCount: 61, estimatedSize: 480 * 1024 },
  { id: 'akkadian', name: 'Akkadian Empire', region: 'Ancient Near East', startYear: -2276, endYear: -2151, color: '#FFA07A', fileCount: 3, estimatedSize: 32 * 1024 },
  { id: 'elam', name: 'Elam', region: 'Ancient Near East', startYear: -3200, endYear: -601, color: '#E6A44C', fileCount: 16, estimatedSize: 96 * 1024 },
  { id: 'babylonian', name: 'Babylonian', region: 'Ancient Near East', startYear: -1781, endYear: -536, color: '#FFB347', fileCount: 18, estimatedSize: 96 * 1024 },
  { id: 'assyrian', name: 'Assyrian Empire', region: 'Ancient Near East', startYear: -1781, endYear: -608, color: '#FF6B6B', fileCount: 20, estimatedSize: 160 * 1024 },
  { id: 'hittite', name: 'Hittite Empire', region: 'Ancient Near East', startYear: -1551, endYear: -1176, color: '#FFAA00', fileCount: 7, estimatedSize: 52 * 1024 },
  { id: 'mitanni', name: 'Mitanni', region: 'Ancient Near East', startYear: -1500, endYear: -1241, color: '#D4A574', fileCount: 3, estimatedSize: 24 * 1024 },

  // Mediterranean (9)
  { id: 'minoan', name: 'Minoan Civilization', region: 'Mediterranean', startYear: -1600, endYear: -1401, color: '#20B2AA', fileCount: 2, estimatedSize: 16 * 1024 },
  { id: 'mycenaean', name: 'Mycenaean Greece', region: 'Mediterranean', startYear: -1500, endYear: -1101, color: '#48D1CC', fileCount: 7, estimatedSize: 48 * 1024 },
  { id: 'phoenician', name: 'Phoenicia', region: 'Mediterranean', startYear: -700, endYear: -616, color: '#9370DB', fileCount: 13, estimatedSize: 64 * 1024 },
  { id: 'etruscan', name: 'Etruscan Civilization', region: 'Mediterranean', startYear: -750, endYear: -265, color: '#DB7093', fileCount: 13, estimatedSize: 72 * 1024 },
  { id: 'greek', name: 'Greek City-States', region: 'Mediterranean', startYear: -1051, endYear: -168, color: '#FFA07A', fileCount: 76, estimatedSize: 1017 * 1024 },
  { id: 'macedonian', name: 'Macedonian Empire', region: 'Mediterranean', startYear: -613, endYear: -168, color: '#FF8866', fileCount: 39, estimatedSize: 436 * 1024 },
  { id: 'carthaginian', name: 'Carthaginian', region: 'Mediterranean', startYear: -641, endYear: -155, color: '#FFAA88', fileCount: 28, estimatedSize: 336 * 1024 },
  { id: 'roman', name: 'Roman Empire', region: 'Mediterranean', startYear: -419, endYear: 476, color: '#FF7777', fileCount: 125, estimatedSize: 4.6 * 1024 * 1024 },
  { id: 'byzantine', name: 'Byzantine Empire', region: 'Mediterranean', startYear: 395, endYear: 1471, color: '#FF99AA', fileCount: 135, estimatedSize: 3.7 * 1024 * 1024 },

  // Persian/Central Asia (5)
  { id: 'achaemenid', name: 'Achaemenid Persia', region: 'Persian/Central Asia', startYear: -546, endYear: -329, color: '#00BFFF', fileCount: 13, estimatedSize: 280 * 1024 },
  { id: 'seleucid', name: 'Seleucid Empire', region: 'Persian/Central Asia', startYear: -317, endYear: -65, color: '#00CED1', fileCount: 32, estimatedSize: 404 * 1024 },
  { id: 'parthian', name: 'Parthian Empire', region: 'Persian/Central Asia', startYear: -202, endYear: 230, color: '#40E0D0', fileCount: 26, estimatedSize: 420 * 1024 },
  { id: 'kushan', name: 'Kushan Empire', region: 'Persian/Central Asia', startYear: 43, endYear: 237, color: '#5F9EA0', fileCount: 11, estimatedSize: 120 * 1024 },
  { id: 'sassanid', name: 'Sassanid Empire', region: 'Persian/Central Asia', startYear: 219, endYear: 642, color: '#7FFFD4', fileCount: 46, estimatedSize: 816 * 1024 },

  // East Asia (4)
  { id: 'shang', name: 'Shang Dynasty', region: 'East Asia', startYear: -1421, endYear: -1051, color: '#FFD700', fileCount: 3, estimatedSize: 20 * 1024 },
  { id: 'zhou', name: 'Zhou Dynasty', region: 'East Asia', startYear: -901, endYear: -256, color: '#FFE135', fileCount: 17, estimatedSize: 94 * 1024 },
  { id: 'qin', name: 'Qin Dynasty', region: 'East Asia', startYear: -216, endYear: -206, color: '#FF5733', fileCount: 3, estimatedSize: 72 * 1024 },
  { id: 'han', name: 'Han Dynasty', region: 'East Asia', startYear: -200, endYear: 230, color: '#FF6347', fileCount: 52, estimatedSize: 548 * 1024 },

  // South Asia (3)
  { id: 'indus_valley', name: 'Indus Valley (Harappan)', region: 'South Asia', startYear: -3000, endYear: -1701, color: '#66CDAA', fileCount: 8, estimatedSize: 64 * 1024 },
  { id: 'maurya', name: 'Maurya Empire', region: 'South Asia', startYear: -317, endYear: -180, color: '#7FFF00', fileCount: 7, estimatedSize: 84 * 1024 },
  { id: 'gupta', name: 'Gupta Empire', region: 'South Asia', startYear: 335, endYear: 550, color: '#00FF7F', fileCount: 13, estimatedSize: 144 * 1024 },

  // Africa (2)
  { id: 'kush', name: 'Kingdom of Kush', region: 'Africa', startYear: 46, endYear: 230, color: '#FF8C00', fileCount: 13, estimatedSize: 108 * 1024 },
  { id: 'axum', name: 'Aksumite Empire', region: 'Africa', startYear: 93, endYear: 1933, color: '#CD853F', fileCount: 28, estimatedSize: 180 * 1024 },

  // Americas (6)
  { id: 'olmec', name: 'Olmec Civilization', region: 'Americas', startYear: -650, endYear: -351, color: '#228B22', fileCount: 2, estimatedSize: 16 * 1024 },
  { id: 'zapotec', name: 'Zapotec Civilization', region: 'Americas', startYear: -500, endYear: 895, color: '#3CB371', fileCount: 7, estimatedSize: 28 * 1024 },
  { id: 'teotihuacan', name: 'Teotihuacan', region: 'Americas', startYear: -50, endYear: 704, color: '#2E8B57', fileCount: 4, estimatedSize: 24 * 1024 },
  { id: 'maya', name: 'Maya Civilization', region: 'Americas', startYear: 6, endYear: 1697, color: '#00FF7F', fileCount: 22, estimatedSize: 48 * 1024 },
  { id: 'aztec', name: 'Aztec Empire', region: 'Americas', startYear: 1434, endYear: 1521, color: '#7CFC00', fileCount: 17, estimatedSize: 60 * 1024 },
  { id: 'inca', name: 'Inca Empire', region: 'Americas', startYear: 1444, endYear: 1567, color: '#7FFF00', fileCount: 8, estimatedSize: 64 * 1024 },

  // Medieval Europe (1)
  { id: 'carolingian', name: 'Carolingian Empire', region: 'Medieval Europe', startYear: 465, endYear: 984, color: '#6495ED', fileCount: 80, estimatedSize: 640 * 1024 },
]

const CACHE_NAME = 'historical-data'
const HISTORICAL_BASE_PATH = '/data/historical'

class EmpireCacheClass {
  /**
   * Get list of available empires
   */
  getAvailableEmpires(): EmpireInfo[] {
    return EMPIRE_INFO
  }

  /**
   * Get empires grouped by region
   */
  getEmpiresByRegion(): Record<string, EmpireInfo[]> {
    const grouped: Record<string, EmpireInfo[]> = {}
    for (const empire of EMPIRE_INFO) {
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
  getEmpireInfo(empireId: string): EmpireInfo | undefined {
    return EMPIRE_INFO.find(e => e.id === empireId)
  }

  /**
   * Get available years for an empire by listing directory
   */
  async getAvailableYears(empireId: string): Promise<number[]> {
    try {
      // Try to fetch index file first
      const response = await fetch(`${HISTORICAL_BASE_PATH}/${empireId}/index.json`)
      if (response.ok) {
        const index = await response.json()
        return index.years || []
      }
    } catch {
      // Fall through to alternative method
    }

    // Fallback: infer from empire info
    const empire = this.getEmpireInfo(empireId)
    if (empire && empire.fileCount > 0) {
      // Generate range based on file count
      const years: number[] = []
      const step = Math.ceil((empire.endYear - empire.startYear) / empire.fileCount)
      for (let y = empire.startYear; y <= empire.endYear; y += step) {
        years.push(y)
      }
      return years
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
    const total = empire.estimatedSize
    let loadedBytes = 0

    // Fetch directory listing or use known file patterns
    try {
      // Try fetching all files by scanning for .geojson files
      const response = await fetch(`${HISTORICAL_BASE_PATH}/${empireId}/`)
      if (response.ok) {
        const html = await response.text()
        // Parse directory listing for .geojson files
        const matches = html.match(/\d+\.geojson/g) || []
        const years = matches.map(m => parseInt(m.replace('.geojson', '')))

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
      }
    } catch {
      // Fallback: try years inferred from empire info
      const years = await this.getAvailableYears(empireId)
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
    }

    // Update offline storage state
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
   * Estimate size for an empire download
   */
  estimateEmpireSize(empireId: string): number {
    const empire = this.getEmpireInfo(empireId)
    return empire?.estimatedSize || 0
  }

  /**
   * Estimate total size for multiple empires
   */
  estimateSize(empireIds: string[]): number {
    return empireIds.reduce((total, id) => total + this.estimateEmpireSize(id), 0)
  }

  /**
   * Get total size of all empires
   */
  getTotalSize(): number {
    return EMPIRE_INFO.reduce((total, e) => total + e.estimatedSize, 0)
  }
}

export const EmpireCache = new EmpireCacheClass()
