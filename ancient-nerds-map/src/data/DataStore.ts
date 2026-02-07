/**
 * DataStore for ANCIENT NERDS Map - Three.js Globe
 *
 * Loads all data from FastAPI backend with offline support.
 * When offline, loads from IndexedDB if available.
 */

import {
  SourceMeta,
  Site,
  SiteDetail,
  DEFAULT_SOURCE_COLORS,
} from '../types/data'
import { config } from '../config'
import { OfflineStorage, CompactSite } from '../services/OfflineStorage'
import { offlineFetch } from '../services/OfflineFetch'

/** API Base URL - from environment config */
const API_BASE_URL = config.api.baseUrl

// =============================================================================
// DataStore Class
// =============================================================================

class DataStoreClass {
  // Cached data
  private sources: Map<string, SourceMeta> = new Map()
  private sitesBySource: Map<string, Site[]> = new Map()
  private siteDetails: Map<string, SiteDetail> = new Map()

  // Loading state
  private isInitialized = false
  private initPromise: Promise<void> | null = null
  private isOfflineMode = false

  // Stats
  private stats = {
    totalSites: 0,
    bySource: {} as Record<string, number>,
    loadedAt: '',
    dataSource: '' as 'postgres' | 'json' | 'offline' | 'error' | '',
  }

  /**
   * Initialize the data store from API.
   */
  async initialize(): Promise<void> {
    if (this.isInitialized) return
    if (this.initPromise) return this.initPromise

    this.initPromise = this._doInitialize()
    await this.initPromise
  }

  private async _doInitialize(): Promise<void> {
    // Check if offline and has cached data
    const isOffline = !navigator.onLine
    const hasOfflineData = await OfflineStorage.isOfflineEnabled()

    if (isOffline && hasOfflineData) {
      await this._initializeFromOffline()
      return
    }

    // PARALLEL FETCH: Load sources and sites simultaneously for faster startup
    // Hardcode default source 'ancient_nerds' to enable parallel fetch
    const DEFAULT_SOURCE = 'ancient_nerds'

    const [sourcesResponse, sitesResponse] = await Promise.all([
      offlineFetch(`${API_BASE_URL}/sources/`),
      offlineFetch(`${API_BASE_URL}/sites/all?limit=1000000&source=${DEFAULT_SOURCE}`)
    ])

    if (!sourcesResponse.ok) {
      // If API fails and we have offline data, use it
      if (hasOfflineData) {
        await this._initializeFromOffline()
        return
      }
      throw new Error(`Failed to load sources: HTTP ${sourcesResponse.status}`)
    }

    if (!sitesResponse.ok) {
      throw new Error(`Failed to load sites: HTTP ${sitesResponse.status}`)
    }

    // Parse both responses in parallel
    const [sourcesData, sitesData] = await Promise.all([
      sourcesResponse.json(),
      sitesResponse.json()
    ])

    for (const source of sourcesData.sources) {
      this.sources.set(source.id, {
        id: source.id,
        name: source.name,
        description: source.description || '',
        color: source.color,
        category: source.category || 'archaeological',
        recordCount: source.count,
        enabled: true,
        isPrimary: source.isPrimary || false,
        enabledByDefault: source.enabledByDefault || false,
        priority: source.priority || 999,
      })
    }


    // Convert compact API format to Site format
    const sites = this._parseSitesData(sitesData.sites)
    this._storeSitesBySource(sites)

    this.stats.totalSites = sitesData.count
    this.stats.loadedAt = new Date().toISOString()
    this.stats.dataSource = sitesData.dataSource || 'json'
    this._updateBySourceStats()

    this.isInitialized = true
    this.isOfflineMode = false
  }

  /**
   * Initialize from offline IndexedDB cache
   */
  private async _initializeFromOffline(): Promise<void> {
    const downloadState = await OfflineStorage.getDownloadState()

    // Create source metadata from cached data
    for (const sourceId of Object.keys(downloadState.sources)) {
      const sourceInfo = downloadState.sources[sourceId]
      this.sources.set(sourceId, {
        id: sourceId,
        name: sourceId, // Will be updated if sources API cached
        description: '',
        color: DEFAULT_SOURCE_COLORS[sourceId] || DEFAULT_SOURCE_COLORS.default,
        category: 'archaeological',
        recordCount: sourceInfo.siteCount,
        enabled: true,
        isPrimary: false,
        enabledByDefault: true,
        priority: 999,
      })
    }

    // Load sites from IndexedDB
    const allSites = await OfflineStorage.getAllSites()
    const sites = this._parseCompactSites(allSites)
    this._storeSitesBySource(sites)

    this.stats.totalSites = sites.length
    this.stats.loadedAt = downloadState.lastUpdated
    this.stats.dataSource = 'offline'
    this._updateBySourceStats()

    this.isInitialized = true
    this.isOfflineMode = true
  }

  /**
   * Parse CompactSite array from IndexedDB to Site array
   */
  private _parseCompactSites(sites: CompactSite[]): Site[] {
    return sites.map(s => ({
      id: s.id,
      name: s.n,
      lat: s.la,
      lon: s.lo,
      sourceId: s.s,
      type: s.t || undefined,
      periodStart: s.p,
      periodEnd: null,
      image: s.i || null,
      location: s.c || undefined,
    }))
  }

  private _storeSitesBySource(sites: Site[]): void {
    for (const site of sites) {
      const existing = this.sitesBySource.get(site.sourceId) || []
      existing.push(site)
      this.sitesBySource.set(site.sourceId, existing)
    }
  }

  /**
   * Add sites for a specific source (called by SourceLoader).
   */
  addSourceSites(sourceId: string, sites: Site[]): void {
    this.sitesBySource.set(sourceId, sites)
    this._updateBySourceStats()
  }

  /**
   * Get IDs of additional sources (not default/primary).
   */
  getAdditionalSourceIds(): string[] {
    const defaultIds = this.getDefaultEnabledSourceIds()
    return Array.from(this.sources.keys()).filter(id => !defaultIds.includes(id))
  }

  private _parseSitesData(sites: Array<{ id: string; n: string; la: number; lo: number; s: string; t: string | null; p: number | null; pn?: string; d?: string; i?: string; c?: string; u?: string; an?: string[] }>): Site[] {
    return sites.map(s => ({
      id: s.id,
      name: s.n,
      lat: s.la,
      lon: s.lo,
      sourceId: s.s,
      type: s.t || undefined,
      periodStart: s.p,
      periodEnd: null,
      period: s.pn || undefined,  // User-edited period name from database
      description: s.d || undefined,
      image: s.i || null,
      location: s.c || undefined,
      sourceUrl: s.u || undefined,
      altNames: s.an || undefined,
    }))
  }

  private _updateBySourceStats(): void {
    const bySource: Record<string, number> = {}
    let total = 0
    for (const [sourceId, sites] of this.sitesBySource) {
      bySource[sourceId] = sites.length
      total += sites.length
    }
    this.stats.bySource = bySource
    this.stats.totalSites = total
  }

  // =============================================================================
  // Getters
  // =============================================================================

  getSites(): Site[] {
    return Array.from(this.sitesBySource.values()).flat()
  }

  getSitesBySource(sourceIds: string[]): Site[] {
    if (sourceIds.length === 0) return this.getSites()
    const result: Site[] = []
    for (const id of sourceIds) {
      const sites = this.sitesBySource.get(id)
      if (sites) result.push(...sites)
    }
    return result
  }

  getSources(): SourceMeta[] {
    return Array.from(this.sources.values())
  }

  getDefaultEnabledSources(): SourceMeta[] {
    const sources = Array.from(this.sources.values())
    const defaultEnabled = sources.filter(s => s.enabledByDefault)
    if (defaultEnabled.length === 0) {
      return sources.filter(s => s.enabled)
    }
    return defaultEnabled
  }

  getDefaultEnabledSourceIds(): string[] {
    return this.getDefaultEnabledSources().map(s => s.id)
  }

  getSource(id: string): SourceMeta | undefined {
    return this.sources.get(id)
  }

  getSourceColor(sourceId: string): string {
    const source = this.sources.get(sourceId)
    return source?.color || DEFAULT_SOURCE_COLORS[sourceId] || DEFAULT_SOURCE_COLORS.default
  }

  getSiteDetail(siteId: string): SiteDetail | undefined {
    return this.siteDetails.get(siteId)
  }

  getStats() {
    return {
      ...this.stats,
      sourcesLoaded: this.sources.size,
      detailsLoaded: this.siteDetails.size,
      isOffline: this.isOfflineMode,
    }
  }

  isReady(): boolean {
    return this.isInitialized
  }

  /**
   * Load only source metadata (lightweight, for pages that don't need full site data).
   */
  async loadSources(): Promise<void> {
    if (this.sources.size > 0) return
    const resp = await fetch(`${API_BASE_URL}/sources/`)
    if (!resp.ok) return
    const data = await resp.json()
    for (const source of data.sources) {
      this.sources.set(source.id, {
        id: source.id,
        name: source.name,
        description: source.description || '',
        color: source.color,
        category: source.category || 'archaeological',
        recordCount: source.count,
        enabled: true,
        isPrimary: source.isPrimary || false,
        enabledByDefault: source.enabledByDefault || false,
        priority: source.priority || 999,
        url: source.url,
      })
    }
  }

  /**
   * Check if currently running in offline mode
   */
  isOffline(): boolean {
    return this.isOfflineMode
  }

  /**
   * Get the current data source (postgres, json, offline, error)
   */
  getDataSource(): 'postgres' | 'json' | 'offline' | 'error' | '' {
    return this.stats.dataSource
  }

  /**
   * Set the data source to error state (API not reachable)
   */
  setDataSourceError(): void {
    this.stats.dataSource = 'error'
  }

  getUniqueSourceIds(): string[] {
    return Array.from(this.sitesBySource.keys()).sort()
  }
}

// =============================================================================
// Singleton Export
// =============================================================================

export const DataStore = new DataStoreClass()
export { DataStoreClass }
