/**
 * Ancient Maps Service
 *
 * Searches the David Rumsey Map Collection API by site name
 */

import { OfflineFetch } from './OfflineFetch'

export interface AncientMap {
  id: string
  title: string
  date: string | null
  thumbnail: string
  fullImage: string
  webUrl: string
}

interface ApiFieldValue {
  fieldName: string
  value: string
}

interface ApiResult {
  id: string
  displayName: string
  urlSize2?: string
  urlSize4?: string
  fieldValues?: ApiFieldValue[]
  iiifManifest?: string
}

interface ApiResponse {
  results?: ApiResult[]
  totalResults?: number
}

// Minimum relevance score to include a map (out of 100)
const MIN_RELEVANCE_SCORE = 25

// Map-related keywords that boost relevance
const MAP_KEYWORDS = [
  'map', 'carte', 'mapa', 'karte', 'plan', 'atlas', 'chart',
  'ancient', 'antique', 'historical', 'historic', 'old',
  'region', 'territory', 'empire', 'kingdom', 'province'
]

/** Normalize string for search comparison (lowercase, remove diacritics) */
function normalizeForSearch(str: string): string {
  return str.toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/\s+/g, ' ').trim()
}

/** Extract country from a location string (last part after comma) */
function extractCountryFromLocation(location: string): string {
  if (!location) return ''
  const parts = location.split(',')
  return parts[parts.length - 1].trim()
}

// Extract search-friendly name from site title
function getPrimaryName(name: string): string {
  // Only split on " - " (space-dash-space), or "(", ","
  let result = name.split(/\s+-\s+|\s*[(,]\s*/)[0].trim()
  // Remove leading articles
  result = result.replace(/^(The|A|An)\s+/i, '')
  // Remove filler words
  result = result.replace(/\b(of|the|at|in|on)\b/gi, ' ')
  // Clean up spaces
  result = result.replace(/\s+/g, ' ').trim()
  return result || name
}

/** Score how relevant a map is to the site (0-100) */
function scoreMapRelevance(
  mapTitle: string,
  siteName: string,
  primaryName: string,
  country: string
): number {
  const normalizedMap = normalizeForSearch(mapTitle)
  const normalizedSite = normalizeForSearch(siteName)
  const normalizedPrimary = normalizeForSearch(primaryName)
  const normalizedCountry = normalizeForSearch(country)

  let score = 0

  // Exact match with full site name
  if (normalizedMap === normalizedSite) {
    score += 100
  }
  // Map title starts with site name
  else if (normalizedMap.startsWith(normalizedSite)) {
    score += 80
  }
  // Map contains full site name
  else if (normalizedMap.includes(normalizedSite)) {
    score += 70
  }
  // Map contains primary name
  else if (normalizedMap.includes(normalizedPrimary)) {
    score += 50
  }
  // Check individual significant words (at least 4 chars)
  else {
    const siteWords = normalizedPrimary.split(' ').filter(w => w.length >= 4)
    const matchedWords = siteWords.filter(word => normalizedMap.includes(word))
    if (matchedWords.length > 0) {
      score += Math.round((matchedWords.length / siteWords.length) * 40)
    }
  }

  // Bonus: contains country name
  if (normalizedCountry && normalizedMap.includes(normalizedCountry)) {
    score += 15
  }

  // Bonus: contains map-related keywords
  const hasMapKeyword = MAP_KEYWORDS.some(kw => normalizedMap.includes(kw))
  if (hasMapKeyword) {
    score += 10
  }

  return Math.min(score, 100)
}

/**
 * Search for maps by site name using David Rumsey API
 */
export async function findMapsForLocation(
  _lat: number,
  _lon: number,
  siteName: string,
  location: string = '',
  limit: number = 50
): Promise<AncientMap[]> {
  // Early return if offline - David Rumsey API requires internet
  if (OfflineFetch.isOffline) {
    return []
  }

  if (!siteName.trim()) {
    return []
  }

  // Extract primary name and country for search
  const primaryName = getPrimaryName(siteName)
  const country = extractCountryFromLocation(location)
  const searchTerm = country ? `${primaryName} ${country}` : primaryName

  const searchQuery = encodeURIComponent(searchTerm)
  const apiUrl = `https://www.davidrumsey.com/luna/servlet/as/search?q=${searchQuery}&os=0&bs=${limit}`

  try {
    const response = await fetch(apiUrl)
    if (!response.ok) {
      console.error('David Rumsey API error:', response.status)
      return []
    }

    const data: ApiResponse = await response.json()

    if (!data.results || data.results.length === 0) {
      return []
    }

    console.log(`Found ${data.results.length} maps for "${searchTerm}"`)

    // Score and filter maps by relevance
    const scoredMaps: Array<{ map: AncientMap; score: number }> = data.results
      .map(result => {
        // Extract date from fieldValues
        const dateField = result.fieldValues?.find(f => f.fieldName === 'Date')
        const date = dateField?.value || null

        // Build web URL from id
        const webUrl = `https://www.davidrumsey.com/luna/servlet/detail/${result.id}`

        const map: AncientMap = {
          id: result.id,
          title: result.displayName || 'Untitled',
          date,
          thumbnail: result.urlSize2 || '',
          fullImage: result.urlSize4 || result.urlSize2 || '',
          webUrl
        }

        if (!map.thumbnail) return null

        // Calculate relevance score
        const score = scoreMapRelevance(map.title, siteName, primaryName, country)
        return { map, score }
      })
      .filter((item): item is { map: AncientMap; score: number } => item !== null)
      // Filter by minimum relevance score
      .filter(item => item.score >= MIN_RELEVANCE_SCORE)
      // Sort by score descending
      .sort((a, b) => b.score - a.score)

    const maps = scoredMaps.map(item => item.map)

    if (maps.length < data.results.length) {
      console.log(`Filtered to ${maps.length} relevant maps (min score: ${MIN_RELEVANCE_SCORE})`)
    }

    return maps
  } catch (error) {
    console.error('Error searching David Rumsey:', error)
    return []
  }
}

/**
 * Preload is no longer needed with API search
 */
export function preloadMaps(): void {
  // No-op - we search on demand now
}
