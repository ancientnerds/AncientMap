import { categorizePeriod } from '../data/sites'
import type { SiteData } from '../data/sites'

// API response shape from /api/sites/{id}
export interface ApiSiteDetail {
  id: string
  name: string
  lat: number
  lon: number
  sourceId: string
  type?: string
  periodStart?: number | null
  periodName?: string
  country?: string
  description?: string
  sourceUrl?: string
}

// Convert API detail response to SiteData - SINGLE SOURCE OF TRUTH
export function apiDetailToSiteData(detail: ApiSiteDetail): SiteData {
  // Validate coordinates - null/undefined/NaN should not default to 0,0 (Atlantic Ocean)
  const hasValidLon = typeof detail.lon === 'number' && !isNaN(detail.lon)
  const hasValidLat = typeof detail.lat === 'number' && !isNaN(detail.lat)

  // Use coordinates only if both are valid numbers, otherwise use a placeholder
  // that will be obvious in the UI (center of map view, but flagged)
  const lon = hasValidLon ? detail.lon : NaN
  const lat = hasValidLat ? detail.lat : NaN

  return {
    id: detail.id,
    title: detail.name || 'Unknown Site',
    coordinates: [lon, lat],
    category: detail.type || 'Unknown',
    period: detail.periodName || categorizePeriod(detail.periodStart),
    periodStart: detail.periodStart,
    location: detail.country || '',
    description: detail.description || '',
    sourceId: detail.sourceId || 'unknown',
    sourceUrl: detail.sourceUrl,
  }
}
