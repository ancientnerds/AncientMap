import { DataStore, type SiteFields } from './DataStore'
import type { Site, SourceMeta } from '../types/data'
import type { DescriptionAi, DescriptionAttribution, DescriptionCitation } from '../types/anRoute'
import {
  SOURCE_COLORS,
  CATEGORY_COLORS,
  PERIOD_COLORS,
  getSourceColor,
  getCategoryColor,
  getPeriodColor,
  getCategoryGroup,
  CATEGORY_GROUP_ORDER,
  type CategoryGroup,
  normalizeSiteType,
} from '../constants/colors'

// Re-export color helpers and constants from centralized constants
export { getCategoryColor, getPeriodColor, getSourceColor, SOURCE_COLORS, CATEGORY_COLORS, PERIOD_COLORS }
export { getCategoryGroup, CATEGORY_GROUP_ORDER, type CategoryGroup, normalizeSiteType }

export interface ImageAttribution {
  photographer?: string
  license?: string
}

export interface ReferenceLink {
  url: string
  title: string
  domain: string
  kind: string
}

export interface SiteData {
  id: string
  title: string
  location: string
  category: string
  period: string
  periodStart?: number | null
  description: string
  image?: string
  imageAttribution?: ImageAttribution
  sourceUrl?: string
  sourceId: string
  coordinates: [number, number]
  cardDescription?: string
  altNames?: string[]
  bestWikiUrl?: string
  sourceLanguage?: string
  referenceLinks?: ReferenceLink[]
  descriptionCitations?: DescriptionCitation[]
  /**
   * The description's AI mark and attribution (api/services/description_provenance.py),
   * where the record came from a live source - /api/sites/{id} or the SSR payload - whose
   * description is the text they describe. The static export does not carry them.
   */
  descriptionAi?: DescriptionAi
  descriptionAttribution?: DescriptionAttribution | null
  /** The card's AI mark, where the card is the one its provenance hashes. */
  cardAi?: DescriptionAi
}

// Period list derived from centralized PERIOD_COLORS
export const ANCIENT_PERIODS = Object.keys(PERIOD_COLORS).filter(p => p !== 'Unknown')

/**
 * Categorize period based on year.
 */
export function categorizePeriod(start: number | null | undefined): string {
  if (start === null || start === undefined) return 'Unknown'
  if (start < -4500) return '< 4500 BC'
  if (start < -3000) return '4500 - 3000 BC'
  if (start < -1500) return '3000 - 1500 BC'
  if (start < -500) return '1500 - 500 BC'
  if (start < 1) return '500 BC - 1 AD'
  if (start < 500) return '1 - 500 AD'
  if (start < 1000) return '500 - 1000 AD'
  if (start < 1500) return '1000 - 1500 AD'
  return '1500+ AD'
}

/**
 * Resolve display period: stored name wins, computed bucket is fallback.
 */
export function resolvePeriod(periodName?: string | null, periodStart?: number | null): string {
  return periodName || categorizePeriod(periodStart) || 'Unknown'
}

/** The SiteData fields the globe payload (`fields=globe`) leaves out. */
export type SiteDetails = Pick<SiteData,
  'description' | 'cardDescription' | 'image' | 'sourceUrl' | 'altNames' |
  'bestWikiUrl' | 'sourceLanguage' | 'referenceLinks' | 'descriptionCitations'>

const DETAIL_KEYS = [
  'description', 'cardDescription', 'image', 'sourceUrl', 'altNames',
  'bestWikiUrl', 'sourceLanguage', 'referenceLinks', 'descriptionCitations',
] as const satisfies ReadonlyArray<keyof SiteDetails>

function siteDetailsOf(site: Site): SiteDetails {
  return {
    description: site.description || '',
    cardDescription: site.cardDescription,
    image: site.imageUrl || site.image || undefined,
    sourceUrl: site.sourceUrl,
    altNames: site.altNames,
    bestWikiUrl: site.bestWikiUrl,
    sourceLanguage: site.sourceLanguage,
    referenceLinks: site.referenceLinks?.map(r => ({
      url: r.u, title: r.t, domain: r.d, kind: r.k,
    })),
    descriptionCitations: site.descriptionCitations,
  }
}

function toSiteData(site: Site): SiteData {
  return {
    id: site.id,
    title: site.name,
    location: site.location || '',
    category: normalizeSiteType(site.type),
    period: resolvePeriod(site.period, site.periodStart),
    periodStart: site.periodStart,
    sourceId: site.sourceId,
    coordinates: [site.lon, site.lat] as [number, number],
    ...siteDetailsOf(site),
  }
}

/**
 * Fetch sites from API via DataStore. `'globe'` loads only the fields the globe draws;
 * the details follow through loadSiteDetails().
 */
export async function fetchSites(fields: SiteFields = 'all'): Promise<SiteData[]> {
  await DataStore.initialize(fields)
  return DataStore.getSites().map(toSiteData)
}

/**
 * The payload the globe starts on. A focus deep link (#focus= / ?focus=) searches for its
 * site's title as soon as the sites arrive; on the globe payload that search would wait
 * for the details, showing every dot and "Searching..." until then. So a focus load takes
 * the full payload, whose details are ready at once, and its first frame shows only the
 * matches, as before. A plain globe load takes the slim payload and the details after.
 */
export function globeSiteFields(focusSiteId: string | null): SiteFields {
  return focusSiteId ? 'all' : 'globe'
}

/** One details map per DataStore result, so every caller merges the same objects. */
const detailsByResult = new WeakMap<Site[], Map<string, SiteDetails>>()

/**
 * Load the detail fields the globe payload left out (one shared request, see
 * DataStore.loadSiteDetails) and resolve with them per site id, for mergeSiteDetails.
 * Every caller gets the same map, so merging it twice changes nothing the second time.
 */
export async function loadSiteDetails(): Promise<Map<string, SiteDetails>> {
  const updated = await DataStore.loadSiteDetails()
  let byId = detailsByResult.get(updated)
  if (!byId) {
    byId = new Map(updated.map(site => [site.id, siteDetailsOf(site)]))
    detailsByResult.set(updated, byId)
  }
  return byId
}

/**
 * Merge loaded details into App's site list. Sites whose details did not change keep
 * their object (and the array stays the same when none changed); changed sites become
 * new objects that keep their `coordinates` array; no site is added or dropped.
 */
export function mergeSiteDetails(prev: SiteData[], byId: ReadonlyMap<string, SiteDetails>): SiteData[] {
  let changed = false
  const next = prev.map(site => {
    const details = byId.get(site.id)
    if (!details || DETAIL_KEYS.every(key => site[key] === details[key])) return site
    changed = true
    return { ...site, ...details }
  })
  return changed ? next : prev
}

/**
 * A site from the bulk payload with its detail fields, for the paths that open a popup
 * from bulk data. A default-source site waits for the detail load (and starts it when it
 * has not started yet) and rejects when that failed. Any other site (an opt-in source,
 * an API search result) already carries its details and comes back unchanged at once.
 */
export async function withSiteDetails(site: SiteData): Promise<SiteData> {
  if (!DataStore.detailsCover(site.id)) return site
  await DataStore.loadSiteDetails()
  const stored = DataStore.getSiteById(site.id)
  return stored ? { ...site, ...siteDetailsOf(stored) } : site
}

export function getSources(): SourceMeta[] {
  return DataStore.getSources()
}

export function getSourceUrl(sourceId: string): string | undefined {
  return DataStore.getSource(sourceId)?.url
}

export function getSourceInfo(sourceId: string): SourceMeta | undefined {
  return DataStore.getSource(sourceId)
}

export function getDefaultEnabledSourceIds(): string[] {
  return DataStore.getDefaultEnabledSourceIds()
}

export function getAdditionalSourceIds(): string[] {
  return DataStore.getAdditionalSourceIds()
}

export function getDataSource(): 'postgres' | 'json' | 'offline' | 'error' | '' {
  return DataStore.getDataSource()
}

export function setDataSourceError(): void {
  DataStore.setDataSourceError()
}

export function addSourceSites(sourceId: string, sites: Site[]): void {
  DataStore.addSourceSites(sourceId, sites)
}

export function getCurrentSites(): SiteData[] {
  return DataStore.getSites().map(toSiteData)
}

interface GeoJSONFeature {
  type: 'Feature'
  geometry: { type: 'Point'; coordinates: [number, number] }
  properties: Record<string, unknown>
}

interface GeoJSONCollection {
  type: 'FeatureCollection'
  features: GeoJSONFeature[]
}

export function sitesToGeoJSON(sites: SiteData[]): GeoJSONCollection {
  return {
    type: 'FeatureCollection',
    features: sites.map(site => ({
      type: 'Feature' as const,
      geometry: {
        type: 'Point' as const,
        coordinates: site.coordinates
      },
      properties: {
        id: site.id,
        Title: site.title,
        Location: site.location,
        Category: site.category,
        Period: site.period,
        Description: site.description,
        Images: site.image
      }
    }))
  }
}
