/**
 * OfflineStorage - IndexedDB abstraction for offline data persistence
 * Uses the 'idb' library for Promise-based IndexedDB access
 */

import { openDB, DBSchema, IDBPDatabase } from 'idb'

// Types for stored data
export interface StoredSiteData {
  sourceId: string
  sites: CompactSite[]
  downloadedAt: string
  totalCount: number
  checksum?: string
}

export interface CompactSite {
  id: string
  n: string      // name
  la: number     // latitude
  lo: number     // longitude
  s: string      // sourceId
  t?: string     // type
  p?: number     // periodStart
  i?: string     // image
  c?: string     // country
}

export interface QueuedContribution {
  id: string
  formData: {
    name: string
    country: string
    lat: number | null
    lon: number | null
    siteType: string
    description: string
    sourceUrl: string
  }
  createdAt: string
  status: 'pending' | 'syncing' | 'error'
  lastError?: string
  retryCount: number
}

export interface DownloadState {
  sources: Record<string, {
    cached: boolean
    downloadedAt: string
    siteCount: number
  }>
  basemapQualities: ('low' | 'normal' | 'high')[]  // Legacy - kept for backward compat
  basemapQuality: 'none' | 'low' | 'normal' | 'high'  // Legacy - kept for backward compat
  basemapItems: string[]  // New: 'satellite' | 'labels'
  layers: string[]  // Vector layers (coastlines, rivers, etc.)
  empires: string[]
  lastUpdated: string
}

// IndexedDB Schema
interface OfflineDBSchema extends DBSchema {
  sites: {
    key: string
    value: StoredSiteData
    indexes: { 'by-downloadedAt': string }
  }
  contributions: {
    key: string
    value: QueuedContribution
    indexes: { 'by-status': string; 'by-createdAt': string }
  }
  metadata: {
    key: string
    value: { key: string; value: unknown }
  }
}

const DB_NAME = 'ancient-map-offline'
const DB_VERSION = 1

class OfflineStorageClass {
  private db: IDBPDatabase<OfflineDBSchema> | null = null
  private initPromise: Promise<void> | null = null

  /**
   * Initialize the database connection
   */
  async init(): Promise<void> {
    if (this.db) return
    if (this.initPromise) return this.initPromise

    this.initPromise = this.doInit()
    return this.initPromise
  }

  private async doInit(): Promise<void> {
    this.db = await openDB<OfflineDBSchema>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        // Sites store - site data by source
        if (!db.objectStoreNames.contains('sites')) {
          const sitesStore = db.createObjectStore('sites', { keyPath: 'sourceId' })
          sitesStore.createIndex('by-downloadedAt', 'downloadedAt')
        }

        // Contributions store - queued offline contributions
        if (!db.objectStoreNames.contains('contributions')) {
          const contribStore = db.createObjectStore('contributions', { keyPath: 'id' })
          contribStore.createIndex('by-status', 'status')
          contribStore.createIndex('by-createdAt', 'createdAt')
        }

        // Metadata store - general key-value storage
        if (!db.objectStoreNames.contains('metadata')) {
          db.createObjectStore('metadata', { keyPath: 'key' })
        }
      }
    })
  }

  private async getDB(): Promise<IDBPDatabase<OfflineDBSchema>> {
    await this.init()
    return this.db!
  }

  // ==================== SITES ====================

  /**
   * Save sites for a source to IndexedDB
   */
  async saveSites(sourceId: string, sites: CompactSite[]): Promise<void> {
    const db = await this.getDB()
    const data: StoredSiteData = {
      sourceId,
      sites,
      downloadedAt: new Date().toISOString(),
      totalCount: sites.length
    }
    await db.put('sites', data)
    await this.updateDownloadState(sourceId, sites.length)
  }

  /**
   * Get sites for a specific source
   */
  async getSites(sourceId: string): Promise<CompactSite[] | null> {
    const db = await this.getDB()
    const data = await db.get('sites', sourceId)
    return data?.sites || null
  }

  /**
   * Get all cached sites (merged from all sources)
   */
  async getAllSites(): Promise<CompactSite[]> {
    const db = await this.getDB()
    const allData = await db.getAll('sites')
    return allData.flatMap(d => d.sites)
  }

  /**
   * Get list of cached source IDs
   */
  async getCachedSourceIds(): Promise<string[]> {
    const db = await this.getDB()
    return db.getAllKeys('sites')
  }

  /**
   * Remove sites for a source
   */
  async removeSites(sourceId: string): Promise<void> {
    const db = await this.getDB()
    await db.delete('sites', sourceId)
    await this.removeFromDownloadState(sourceId)
  }

  /**
   * Clear all cached sites
   */
  async clearAllSites(): Promise<void> {
    const db = await this.getDB()
    await db.clear('sites')
    await this.setMetadata('download-state', {
      sources: {},
      basemapQuality: 'none',
      empires: [],
      lastUpdated: new Date().toISOString()
    })
  }

  // ==================== CONTRIBUTIONS ====================

  /**
   * Queue a contribution for later sync
   */
  async queueContribution(contribution: Omit<QueuedContribution, 'id' | 'createdAt' | 'status' | 'retryCount'>): Promise<string> {
    const db = await this.getDB()
    const id = crypto.randomUUID()
    const queued: QueuedContribution = {
      id,
      formData: contribution.formData,
      createdAt: new Date().toISOString(),
      status: 'pending',
      retryCount: 0
    }
    await db.put('contributions', queued)
    return id
  }

  /**
   * Get all pending contributions
   */
  async getPendingContributions(): Promise<QueuedContribution[]> {
    const db = await this.getDB()
    return db.getAllFromIndex('contributions', 'by-status', 'pending')
  }

  /**
   * Get count of pending contributions
   */
  async getPendingContributionsCount(): Promise<number> {
    const db = await this.getDB()
    const pending = await db.getAllFromIndex('contributions', 'by-status', 'pending')
    return pending.length
  }

  /**
   * Update contribution status
   */
  async updateContributionStatus(id: string, status: QueuedContribution['status'], error?: string): Promise<void> {
    const db = await this.getDB()
    const contribution = await db.get('contributions', id)
    if (contribution) {
      contribution.status = status
      if (error) contribution.lastError = error
      await db.put('contributions', contribution)
    }
  }

  /**
   * Increment retry count for a contribution
   */
  async incrementRetryCount(id: string): Promise<void> {
    const db = await this.getDB()
    const contribution = await db.get('contributions', id)
    if (contribution) {
      contribution.retryCount++
      contribution.status = 'error'
      await db.put('contributions', contribution)
    }
  }

  /**
   * Remove a contribution (after successful sync)
   */
  async removeContribution(id: string): Promise<void> {
    const db = await this.getDB()
    await db.delete('contributions', id)
  }

  /**
   * Clear all contributions
   */
  async clearAllContributions(): Promise<void> {
    const db = await this.getDB()
    await db.clear('contributions')
  }

  // ==================== METADATA ====================

  /**
   * Set a metadata value
   */
  async setMetadata<T>(key: string, value: T): Promise<void> {
    const db = await this.getDB()
    await db.put('metadata', { key, value })
  }

  /**
   * Get a metadata value
   */
  async getMetadata<T>(key: string): Promise<T | null> {
    const db = await this.getDB()
    const data = await db.get('metadata', key)
    return (data?.value as T) || null
  }

  /**
   * Get current download state
   */
  async getDownloadState(): Promise<DownloadState> {
    const state = await this.getMetadata<DownloadState>('download-state')
    return state || {
      sources: {},
      basemapQualities: [],
      basemapQuality: 'none',
      basemapItems: [],
      layers: [],
      empires: [],
      lastUpdated: new Date().toISOString()
    }
  }

  /**
   * Update download state for a source
   */
  private async updateDownloadState(sourceId: string, siteCount: number): Promise<void> {
    const state = await this.getDownloadState()
    state.sources[sourceId] = {
      cached: true,
      downloadedAt: new Date().toISOString(),
      siteCount
    }
    state.lastUpdated = new Date().toISOString()
    await this.setMetadata('download-state', state)
  }

  /**
   * Remove source from download state
   */
  private async removeFromDownloadState(sourceId: string): Promise<void> {
    const state = await this.getDownloadState()
    delete state.sources[sourceId]
    state.lastUpdated = new Date().toISOString()
    await this.setMetadata('download-state', state)
  }

  /**
   * Set basemap quality in download state (legacy single quality)
   */
  async setBasemapQuality(quality: DownloadState['basemapQuality']): Promise<void> {
    const state = await this.getDownloadState()
    state.basemapQuality = quality
    state.lastUpdated = new Date().toISOString()
    await this.setMetadata('download-state', state)
  }

  /**
   * Add a basemap quality to download state (for LOD support)
   */
  async addBasemapQuality(quality: 'low' | 'normal' | 'high'): Promise<void> {
    const state = await this.getDownloadState()
    if (!state.basemapQualities) state.basemapQualities = []
    if (!state.basemapQualities.includes(quality)) {
      state.basemapQualities.push(quality)
    }
    state.lastUpdated = new Date().toISOString()
    await this.setMetadata('download-state', state)
  }

  /**
   * Remove a basemap quality from download state
   */
  async removeBasemapQuality(quality: 'low' | 'normal' | 'high'): Promise<void> {
    const state = await this.getDownloadState()
    if (state.basemapQualities) {
      state.basemapQualities = state.basemapQualities.filter(q => q !== quality)
    }
    state.lastUpdated = new Date().toISOString()
    await this.setMetadata('download-state', state)
  }

  /**
   * Add a basemap item to download state (satellite, labels)
   */
  async addBasemapItem(itemId: string): Promise<void> {
    const state = await this.getDownloadState()
    if (!state.basemapItems) state.basemapItems = []
    if (!state.basemapItems.includes(itemId)) {
      state.basemapItems.push(itemId)
    }
    state.lastUpdated = new Date().toISOString()
    await this.setMetadata('download-state', state)
  }

  /**
   * Remove a basemap item from download state
   */
  async removeBasemapItem(itemId: string): Promise<void> {
    const state = await this.getDownloadState()
    if (state.basemapItems) {
      state.basemapItems = state.basemapItems.filter(id => id !== itemId)
    }
    state.lastUpdated = new Date().toISOString()
    await this.setMetadata('download-state', state)
  }

  /**
   * Add a vector layer to download state
   */
  async addDownloadedLayer(layerId: string): Promise<void> {
    const state = await this.getDownloadState()
    if (!state.layers) state.layers = []
    if (!state.layers.includes(layerId)) {
      state.layers.push(layerId)
    }
    state.lastUpdated = new Date().toISOString()
    await this.setMetadata('download-state', state)
  }

  /**
   * Remove a vector layer from download state
   */
  async removeDownloadedLayer(layerId: string): Promise<void> {
    const state = await this.getDownloadState()
    if (state.layers) {
      state.layers = state.layers.filter(id => id !== layerId)
    }
    state.lastUpdated = new Date().toISOString()
    await this.setMetadata('download-state', state)
  }

  /**
   * Add empire to download state
   */
  async addDownloadedEmpire(empireId: string): Promise<void> {
    const state = await this.getDownloadState()
    if (!state.empires.includes(empireId)) {
      state.empires.push(empireId)
    }
    state.lastUpdated = new Date().toISOString()
    await this.setMetadata('download-state', state)
  }

  /**
   * Remove empire from download state
   */
  async removeDownloadedEmpire(empireId: string): Promise<void> {
    const state = await this.getDownloadState()
    state.empires = state.empires.filter(id => id !== empireId)
    state.lastUpdated = new Date().toISOString()
    await this.setMetadata('download-state', state)
  }

  // ==================== STORAGE INFO ====================

  /**
   * Get estimated storage usage
   */
  async getStorageEstimate(): Promise<{ used: number; quota: number }> {
    if ('storage' in navigator && 'estimate' in navigator.storage) {
      const estimate = await navigator.storage.estimate()
      return {
        used: estimate.usage || 0,
        quota: estimate.quota || 0
      }
    }
    return { used: 0, quota: 0 }
  }

  /**
   * Check if offline mode is enabled (has cached data)
   */
  async isOfflineEnabled(): Promise<boolean> {
    const state = await this.getDownloadState()
    return Object.keys(state.sources).length > 0 || state.basemapQuality !== 'none'
  }

  /**
   * Get all image URLs for a cached source.
   * Used for pre-downloading hero images before going offline.
   */
  async getImageUrlsForSource(sourceId: string): Promise<string[]> {
    const sites = await this.getSites(sourceId)
    if (!sites) return []

    // Extract image URLs (stored as 'i' in compact format)
    return sites
      .filter(site => site.i && site.i.trim())
      .map(site => site.i!)
  }

  /**
   * Clear all offline data
   */
  async clearAll(): Promise<void> {
    const db = await this.getDB()
    await db.clear('sites')
    await db.clear('contributions')
    await db.clear('metadata')
  }
}

// Singleton export
export const OfflineStorage = new OfflineStorageClass()
