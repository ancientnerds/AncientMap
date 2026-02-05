import { DataStore } from './DataStore'
import { SourceMeta } from '../types/data'
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
} from '../constants/colors'

// Re-export color helpers and constants from centralized constants
export { getCategoryColor, getPeriodColor, getSourceColor, SOURCE_COLORS, CATEGORY_COLORS, PERIOD_COLORS }
export { getCategoryGroup, CATEGORY_GROUP_ORDER, type CategoryGroup }

export interface ImageAttribution {
  photographer?: string
  license?: string
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
  altNames?: string[]
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
 * Fetch sites from API via DataStore.
 */
export async function fetchSites(): Promise<SiteData[]> {
  await DataStore.initialize()

  const sites = DataStore.getSites()
  return sites.map(site => ({
    id: site.id,
    title: site.name,
    location: site.location || '',
    category: site.type || 'Unknown',
    period: site.period || categorizePeriod(site.periodStart),
    periodStart: site.periodStart,
    description: site.description || '',
    image: site.imageUrl || site.image || undefined,
    sourceUrl: site.sourceUrl,
    sourceId: site.sourceId,
    coordinates: [site.lon, site.lat] as [number, number],
    altNames: site.altNames,
  }))
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

export function addSourceSites(sourceId: string, sites: import('../types/data').Site[]): void {
  DataStore.addSourceSites(sourceId, sites)
}

export function getCurrentSites(): SiteData[] {
  const sites = DataStore.getSites()
  return sites.map(site => ({
    id: site.id,
    title: site.name,
    location: site.location || '',
    category: site.type || 'Unknown',
    period: site.period || categorizePeriod(site.periodStart),
    periodStart: site.periodStart,
    description: site.description || '',
    image: site.imageUrl || site.image || undefined,
    sourceUrl: site.sourceUrl,
    sourceId: site.sourceId,
    coordinates: [site.lon, site.lat] as [number, number],
    altNames: site.altNames,
  }))
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
