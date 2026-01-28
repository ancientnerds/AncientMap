/**
 * EmpireCache - Handles caching of historical empire boundary GeoJSON files
 * Uses Service Worker cache for GeoJSON data
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

// Empire definitions matching Globe.tsx EMPIRES constant with accurate file counts/sizes
const EMPIRE_INFO: EmpireInfo[] = [
  // Ancient Near East
  { id: 'egyptian', name: 'Egyptian Empire', region: 'Ancient Near East', startYear: -2401, endYear: -29, color: '#FFD700', fileCount: 44, estimatedSize: 480 * 1024 },
  { id: 'akkadian', name: 'Akkadian Empire', region: 'Ancient Near East', startYear: -2276, endYear: -2151, color: '#FFA07A', fileCount: 4, estimatedSize: 32 * 1024 },
  { id: 'babylonian', name: 'Babylonian', region: 'Ancient Near East', startYear: -1781, endYear: -536, color: '#FFB347', fileCount: 19, estimatedSize: 96 * 1024 },
  { id: 'assyrian', name: 'Assyrian Empire', region: 'Ancient Near East', startYear: -1781, endYear: -608, color: '#FF6B6B', fileCount: 21, estimatedSize: 160 * 1024 },
  { id: 'hittite', name: 'Hittite Empire', region: 'Ancient Near East', startYear: -1551, endYear: -1176, color: '#FFAA00', fileCount: 8, estimatedSize: 52 * 1024 },

  // Mediterranean
  { id: 'roman', name: 'Roman Empire', region: 'Mediterranean', startYear: -419, endYear: 476, color: '#FF7777', fileCount: 123, estimatedSize: 4.6 * 1024 * 1024 },
  { id: 'greek', name: 'Greek City-States', region: 'Mediterranean', startYear: -1051, endYear: -168, color: '#FFA07A', fileCount: 71, estimatedSize: 1017 * 1024 },
  { id: 'macedonian', name: 'Macedonian Empire', region: 'Mediterranean', startYear: -613, endYear: -168, color: '#FF8866', fileCount: 40, estimatedSize: 436 * 1024 },
  { id: 'byzantine', name: 'Byzantine Empire', region: 'Mediterranean', startYear: 395, endYear: 1471, color: '#FF99AA', fileCount: 132, estimatedSize: 3.7 * 1024 * 1024 },
  { id: 'carthaginian', name: 'Carthaginian', region: 'Mediterranean', startYear: -641, endYear: -155, color: '#FFAA88', fileCount: 29, estimatedSize: 336 * 1024 },

  // Persian/Central Asia
  { id: 'achaemenid', name: 'Achaemenid Persia', region: 'Persian/Central Asia', startYear: -546, endYear: -329, color: '#00BFFF', fileCount: 14, estimatedSize: 280 * 1024 },
  { id: 'parthian', name: 'Parthian Empire', region: 'Persian/Central Asia', startYear: -202, endYear: 230, color: '#40E0D0', fileCount: 27, estimatedSize: 420 * 1024 },
  { id: 'sassanid', name: 'Sassanid Empire', region: 'Persian/Central Asia', startYear: 219, endYear: 642, color: '#7FFFD4', fileCount: 47, estimatedSize: 816 * 1024 },
  { id: 'seleucid', name: 'Seleucid Empire', region: 'Persian/Central Asia', startYear: -317, endYear: -65, color: '#00CED1', fileCount: 33, estimatedSize: 404 * 1024 },
  { id: 'mongol', name: 'Mongol Empire', region: 'Persian/Central Asia', startYear: 1207, endYear: 1693, color: '#F0E68C', fileCount: 53, estimatedSize: 1.2 * 1024 * 1024 },
  { id: 'timurid', name: 'Timurid Empire', region: 'Persian/Central Asia', startYear: 1379, endYear: 1504, color: '#DDA0DD', fileCount: 18, estimatedSize: 232 * 1024 },

  // East Asia
  { id: 'shang', name: 'Shang Dynasty', region: 'East Asia', startYear: -1421, endYear: -1051, color: '#FFD700', fileCount: 4, estimatedSize: 20 * 1024 },
  { id: 'zhou', name: 'Zhou Dynasty', region: 'East Asia', startYear: -901, endYear: -256, color: '#FFE135', fileCount: 18, estimatedSize: 94 * 1024 },
  { id: 'qin', name: 'Qin Dynasty', region: 'East Asia', startYear: -216, endYear: -206, color: '#FF5733', fileCount: 4, estimatedSize: 72 * 1024 },
  { id: 'han', name: 'Han Dynasty', region: 'East Asia', startYear: -200, endYear: 230, color: '#FF6347', fileCount: 28, estimatedSize: 548 * 1024 },
  { id: 'tang', name: 'Tang Dynasty', region: 'East Asia', startYear: 624, endYear: 905, color: '#FF7F50', fileCount: 33, estimatedSize: 680 * 1024 },
  { id: 'song', name: 'Song Dynasty', region: 'East Asia', startYear: 961, endYear: 1275, color: '#FFA500', fileCount: 16, estimatedSize: 208 * 1024 },
  { id: 'ming', name: 'Ming Dynasty', region: 'East Asia', startYear: 1379, endYear: 1643, color: '#FFD700', fileCount: 27, estimatedSize: 544 * 1024 },
  { id: 'qing', name: 'Qing Dynasty', region: 'East Asia', startYear: 1646, endYear: 1911, color: '#FFB90F', fileCount: 68, estimatedSize: 2.2 * 1024 * 1024 },

  // South Asia
  { id: 'maurya', name: 'Maurya Empire', region: 'South Asia', startYear: -317, endYear: -180, color: '#7FFF00', fileCount: 8, estimatedSize: 84 * 1024 },
  { id: 'gupta', name: 'Gupta Empire', region: 'South Asia', startYear: 335, endYear: 550, color: '#00FF7F', fileCount: 14, estimatedSize: 144 * 1024 },
  { id: 'chola', name: 'Chola Dynasty', region: 'South Asia', startYear: 867, endYear: 1254, color: '#7CFC00', fileCount: 29, estimatedSize: 148 * 1024 },
  { id: 'mughal', name: 'Mughal Empire', region: 'South Asia', startYear: 1465, endYear: 1857, color: '#ADFF2F', fileCount: 70, estimatedSize: 700 * 1024 },

  // Southeast Asia
  { id: 'khmer', name: 'Khmer Empire', region: 'Southeast Asia', startYear: 802, endYear: 1431, color: '#98FB98', fileCount: 16, estimatedSize: 124 * 1024 },
  { id: 'majapahit', name: 'Majapahit Empire', region: 'Southeast Asia', startYear: 1318, endYear: 1517, color: '#90EE90', fileCount: 11, estimatedSize: 136 * 1024 },
  { id: 'srivijaya', name: 'Srivijaya', region: 'Southeast Asia', startYear: 677, endYear: 1289, color: '#00FA9A', fileCount: 9, estimatedSize: 72 * 1024 },

  // Africa
  { id: 'kush', name: 'Kingdom of Kush', region: 'Africa', startYear: 46, endYear: 230, color: '#FF8C00', fileCount: 12, estimatedSize: 108 * 1024 },
  { id: 'ghana', name: 'Ghana Empire', region: 'Africa', startYear: 938, endYear: 1231, color: '#F0E68C', fileCount: 4, estimatedSize: 20 * 1024 },
  { id: 'mali', name: 'Mali Empire', region: 'Africa', startYear: 1238, endYear: 1610, color: '#FFDAB9', fileCount: 10, estimatedSize: 64 * 1024 },
  { id: 'songhai', name: 'Songhai Empire', region: 'Africa', startYear: 1465, endYear: 1605, color: '#FFA07A', fileCount: 9, estimatedSize: 38 * 1024 },

  // Americas
  { id: 'maya', name: 'Maya Civilization', region: 'Americas', startYear: 6, endYear: 844, color: '#00FF7F', fileCount: 6, estimatedSize: 28 * 1024 },
  { id: 'aztec', name: 'Aztec Empire', region: 'Americas', startYear: 1434, endYear: 1521, color: '#7CFC00', fileCount: 13, estimatedSize: 60 * 1024 },
  { id: 'inca', name: 'Inca Empire', region: 'Americas', startYear: 1444, endYear: 1567, color: '#7FFF00', fileCount: 9, estimatedSize: 64 * 1024 },

  // Medieval Europe
  { id: 'hre', name: 'Holy Roman Empire', region: 'Medieval Europe', startYear: 965, endYear: 1806, color: '#87CEFA', fileCount: 132, estimatedSize: 2.8 * 1024 * 1024 },

  // Islamic
  { id: 'umayyad', name: 'Umayyad Caliphate', region: 'Islamic', startYear: 658, endYear: 755, color: '#00FF7F', fileCount: 16, estimatedSize: 400 * 1024 },
  { id: 'abbasid', name: 'Abbasid Caliphate', region: 'Islamic', startYear: 750, endYear: 1254, color: '#7CFC00', fileCount: 41, estimatedSize: 852 * 1024 },
  { id: 'fatimid', name: 'Fatimid Caliphate', region: 'Islamic', startYear: 916, endYear: 1172, color: '#00FF00', fileCount: 20, estimatedSize: 260 * 1024 },
  { id: 'ayyubid', name: 'Ayyubid Dynasty', region: 'Islamic', startYear: 1182, endYear: 1245, color: '#32CD32', fileCount: 9, estimatedSize: 128 * 1024 },
  { id: 'ottoman', name: 'Ottoman Empire', region: 'Islamic', startYear: 1315, endYear: 1922, color: '#00FA9A', fileCount: 139, estimatedSize: 4.1 * 1024 * 1024 },
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
