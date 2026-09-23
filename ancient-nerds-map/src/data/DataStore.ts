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
import { CACHE_BUSTER } from '../constants/buildInfo'

/** API Base URL - from environment config */
const API_BASE_URL = config.api.baseUrl

/**
 * The source the first request loads. Hardcoded because enabledByDefault is only
 * known after the sources load, and both requests run in parallel.
 */
const DEFAULT_SOURCE = 'ancient_nerds'

/**
 * Which site fields `/api/sites/all` sends (api/routes/sites.py `fields`): `globe` only
 * what the dots, filters, tooltips and lists draw; `all` the details as well.
 */
export type SiteFields = 'globe' | 'all'

/**
 * The default source's bulk payload. The service worker's `api-sites-globe` rule
 * (src/pwa/runtimeCaching.ts) keys on this query shape.
 */
function defaultSourceSitesUrl(fields: SiteFields): string {
  return `${API_BASE_URL}/sites/all?limit=100000&source=${DEFAULT_SOURCE}&fields=${fields}&${CACHE_BUSTER}`
}

/**
 * One site of `/api/sites/all`. `fields=globe` sends only id, n, la, lo, s, t, p, pn, c;
 * a pinned snapshot may lack t, p, pn and c as well, so they count as null when absent.
 */
interface ApiSite {
  id: string
  n: string
  la: number
  lo: number
  s: string
  t?: string | null
  p?: number | null
  pn?: string
  c?: string
  d?: string
  cd?: string
  i?: string
  u?: string
  an?: string[]
  wu?: string
  sl?: string
  rf?: Array<{ u: string; t: string; d: string; k: string }>
  dc?: Array<{ n: number; url: string; title: string; domain: string }>
}

/** The fields `fields=globe` leaves out (the ones search and popups read). */
type SiteDetailFields = Pick<Site,
  'description' | 'cardDescription' | 'image' | 'sourceUrl' | 'altNames' |
  'bestWikiUrl' | 'sourceLanguage' | 'referenceLinks' | 'descriptionCitations'>

function detailFieldsOf(s: ApiSite): SiteDetailFields {
  return {
    description: s.d || undefined,
    cardDescription: s.cd || undefined,
    image: s.i || null,
    sourceUrl: s.u || undefined,
    altNames: s.an || undefined,
    bestWikiUrl: s.wu || undefined,
    sourceLanguage: s.sl || undefined,
    referenceLinks: s.rf || undefined,
    descriptionCitations: s.dc || undefined,
  }
}

function toSite(s: ApiSite): Site {
  return {
    id: s.id,
    name: s.n,
    lat: s.la,
    lon: s.lo,
    sourceId: s.s,
    type: s.t || undefined,
    periodStart: s.p ?? null,
    periodEnd: null,
    period: s.pn || undefined,  // User-edited period name from database
    location: s.c || undefined,
    ...detailFieldsOf(s),
  }
}

// =============================================================================
// DataStore Class
// =============================================================================

class DataStoreClass {
  // Cached data
  private sources: Map<string, SourceMeta> = new Map()
  private sitesBySource: Map<string, Site[]> = new Map()
  private sitesById: Map<string, Site> = new Map()
  private siteDetails: Map<string, SiteDetail> = new Map()

  // Loading state
  private isInitialized = false
  private initPromise: Promise<void> | null = null
  private isOfflineMode = false
  private hasSiteDetails = false
  private detailsPromise: Promise<Site[]> | null = null

  // Stats
  private stats = {
    totalSites: 0,
    bySource: {} as Record<string, number>,
    loadedAt: '',
    dataSource: '' as 'postgres' | 'json' | 'offline' | 'error' | '',
  }

  /**
   * Initialize the data store from API.
   *
   * `fields` picks the default source's payload: the globe starts on `'globe'` and
   * fetches the details later through loadSiteDetails(); pages that render or search
   * descriptions from the start (SearchPage) keep `'all'`. The first call decides.
   */
  async initialize(fields: SiteFields = 'all'): Promise<void> {
    if (this.isInitialized) return
    if (this.initPromise) return this.initPromise

    this.initPromise = this._doInitialize(fields)
    await this.initPromise
  }

  private async _doInitialize(fields: SiteFields): Promise<void> {
    // Check if offline and has cached data
    const isOffline = !navigator.onLine
    const hasOfflineData = await OfflineStorage.isOfflineEnabled()

    if (isOffline && hasOfflineData) {
      await this._initializeFromOffline()
      return
    }

    // PARALLEL FETCH: Load sources + initial sites simultaneously for faster startup
    const [sourcesResponse, sitesResponse] = await Promise.all([
      offlineFetch(`${API_BASE_URL}/sources/?${CACHE_BUSTER}`),
      offlineFetch(defaultSourceSitesUrl(fields)),
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
    const sites = (sitesData.sites as ApiSite[]).map(toSite)
    this._storeSitesBySource(sites)

    this.stats.totalSites = sitesData.count
    this.stats.loadedAt = new Date().toISOString()
    this.stats.dataSource = sitesData.dataSource || 'json'
    this._updateBySourceStats()

    this.hasSiteDetails = fields === 'all'
    this.isInitialized = true
    this.isOfflineMode = false
  }

  /**
   * Fetch the default source's detail fields that `initialize('globe')` left out and
   * assign them onto the sites already held (same objects). Only detail fields are
   * written, never position, name, type, period or country, and a site the first
   * payload did not have is ignored: the two requests can come from different cache
   * generations, and no dot may move or appear. Resolves with the updated sites.
   *
   * Memoised: every caller shares one request, and a failure stays a failure (the
   * caller reports it; there is no retry). Nothing to fetch after `initialize('all')`
   * or in offline mode, which has no details and no network.
   */
  loadSiteDetails(): Promise<Site[]> {
    const init = this.initPromise
    if (!init) return Promise.reject(new Error('DataStore.loadSiteDetails() called before initialize()'))
    this.detailsPromise ??= this._loadSiteDetails(init)
    return this.detailsPromise
  }

  private async _loadSiteDetails(init: Promise<void>): Promise<Site[]> {
    await init
    if (this.hasSiteDetails) return []

    const response = await offlineFetch(defaultSourceSitesUrl('all'))
    if (!response.ok) {
      throw new Error(`Failed to load site details: HTTP ${response.status}`)
    }
    const data: { sites: ApiSite[] } = await response.json()

    const updated: Site[] = []
    for (const apiSite of data.sites) {
      const site = this.sitesById.get(apiSite.id)
      if (!site) continue
      Object.assign(site, detailFieldsOf(apiSite))
      updated.push(site)
    }
    this.hasSiteDetails = true
    return updated
  }

  /** True once the sites carry their detail fields (see loadSiteDetails()). */
  get detailsReady(): boolean {
    return this.hasSiteDetails
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
    // The compact offline records are the API's site keys without details.
    const allSites: CompactSite[] = await OfflineStorage.getAllSites()
    const sites = allSites.map(toSite)
    this._storeSitesBySource(sites)

    this.stats.totalSites = sites.length
    this.stats.loadedAt = downloadState.lastUpdated
    this.stats.dataSource = 'offline'
    this._updateBySourceStats()

    // Offline data never had details and there is no network to fetch them.
    this.hasSiteDetails = true
    this.isInitialized = true
    this.isOfflineMode = true
  }

  private _storeSitesBySource(sites: Site[]): void {
    for (const site of sites) {
      const existing = this.sitesBySource.get(site.sourceId) || []
      existing.push(site)
      this.sitesBySource.set(site.sourceId, existing)
      this.sitesById.set(site.id, site)
    }
  }

  /**
   * Add sites for a specific source (called by SourceLoader).
   */
  addSourceSites(sourceId: string, sites: Site[]): void {
    for (const site of this.sitesBySource.get(sourceId) ?? []) this.sitesById.delete(site.id)
    this.sitesBySource.set(sourceId, sites)
    for (const site of sites) this.sitesById.set(site.id, site)
    this._updateBySourceStats()
  }

  /**
   * Get IDs of additional sources (not default/primary).
   */
  getAdditionalSourceIds(): string[] {
    const defaultIds = this.getDefaultEnabledSourceIds()
    return Array.from(this.sources.keys()).filter(id => !defaultIds.includes(id))
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

  getSiteById(id: string): Site | undefined {
    return this.sitesById.get(id)
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
    const resp = await fetch(`${API_BASE_URL}/sources/?${CACHE_BUSTER}`)
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
   * May the interactive app take over a server-rendered page?
   *
   * This is the gate SitePage checks before it swaps the static site record
   * for SitePopup. Google's renderer applies robots.txt to a page's own
   * fetches, and /api/app/interactive is disallowed there (Disallow: /api/,
   * no Allow for it) — so for Googlebot the probe rejects, the answer is
   * false, and the record stays. What Google then indexes is the SSR content
   * (hero, facts, cited description) rather than a popup whose robots-blocked
   * galleries read "No photos found / 0 sources returned results", which its
   * Soft-404 classifier took at face value on ~2,100 detail pages (GSC,
   * 2026-09-05). Until 2026-09-15 the gate was the source registry itself,
   * which kept /api/sources/ blocked and left /search.html and /globe.html
   * stuck on "LOADING" in Google's render. Never throws: an unreachable
   * probe is an answer, not an error. The registry is loaded alongside
   * because the popup header needs it.
   */
  async interactiveAllowed(): Promise<boolean> {
    try {
      const probe = await fetch(`${API_BASE_URL}/app/interactive`, { cache: 'no-store' })
      if (!probe.ok) return false
      await this.loadSources()
    } catch {
      return false
    }
    return this.sources.size > 0
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
