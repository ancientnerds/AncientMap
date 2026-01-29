/**
 * Sketchfab Service
 *
 * Searches the Sketchfab API for 3D models matching site names
 */

import { OfflineFetch } from './OfflineFetch'

export interface SketchfabModel {
  uid: string
  name: string
  thumbnail: string
  embedUrl: string
  viewerUrl: string
  creator: string
  creatorUrl: string
  likeCount: number
  viewCount: number
}

interface ApiThumbnail {
  url: string
  width: number
  height: number
}

interface ApiUser {
  displayName: string
  username: string
  profileUrl?: string
}

interface ApiResult {
  uid: string
  name: string
  thumbnails?: {
    images?: ApiThumbnail[]
  }
  user?: ApiUser
  likeCount?: number
  viewCount?: number
  embedUrl?: string
  viewerUrl?: string
}

interface ApiResponse {
  results?: ApiResult[]
  cursors?: {
    next?: string
  }
}

// Simple in-memory cache to reduce API calls
const searchCache = new Map<string, { models: SketchfabModel[]; timestamp: number }>()
const CACHE_TTL = 15 * 60 * 1000 // 15 minutes

// Minimum relevance score to include a model (out of 100)
const MIN_RELEVANCE_SCORE = 30

// Archaeology-related keywords that boost relevance
const ARCHAEOLOGY_KEYWORDS = [
  'ancient', 'archaeological', 'archaeology', 'ruins', 'temple', 'tomb',
  'pyramid', 'monument', 'historic', 'historical', 'heritage', 'excavation',
  'artifact', 'artefact', 'relic', 'antique', 'medieval', 'roman', 'greek',
  'egyptian', 'mesopotamian', 'byzantine', 'ottoman', 'islamic', 'christian',
  'mosque', 'church', 'cathedral', 'palace', 'fortress', 'castle', 'citadel'
]

/** Normalize string for search comparison (lowercase, remove diacritics) */
function normalizeForSearch(str: string): string {
  return str.toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '') // Remove diacritics
    .replace(/\s+/g, ' ').trim()
}

// Extract search-friendly name from site title
// "The Great Pyramid of Giza" -> "Great Pyramid Giza"
// "Al-Rabadha" stays as "Al-Rabadha" (hyphen within word preserved)
function getPrimaryName(name: string): string {
  // 1. Only split on " - " (space-dash-space) for subtitles, or "(", ","
  // This preserves hyphenated names like "Al-Rabadha", "Tel-Aviv"
  let result = name.split(/\s+-\s+|\s*[(,]\s*/)[0].trim()

  // 2. Remove leading articles
  result = result.replace(/^(The|A|An)\s+/i, '')

  // 3. Remove filler words (prepositions/articles in middle)
  result = result.replace(/\b(of|the|at|in|on)\b/gi, ' ')

  // 4. Clean up extra spaces
  result = result.replace(/\s+/g, ' ').trim()

  return result || name
}

/** Score how relevant a model is to the site (0-100) */
function scoreModelRelevance(
  modelName: string,
  siteName: string,
  primaryName: string,
  country: string
): number {
  const normalizedModel = normalizeForSearch(modelName)
  const normalizedSite = normalizeForSearch(siteName)
  const normalizedPrimary = normalizeForSearch(primaryName)
  const normalizedCountry = normalizeForSearch(country)

  let score = 0

  // Exact match with full site name (highest relevance)
  if (normalizedModel === normalizedSite) {
    score += 100
  }
  // Model starts with site name
  else if (normalizedModel.startsWith(normalizedSite)) {
    score += 80
  }
  // Model contains full site name
  else if (normalizedModel.includes(normalizedSite)) {
    score += 70
  }
  // Model contains primary name (without articles/prepositions)
  else if (normalizedModel.includes(normalizedPrimary)) {
    score += 50
  }
  // Check individual significant words (at least 4 chars)
  else {
    const siteWords = normalizedPrimary.split(' ').filter(w => w.length >= 4)
    const matchedWords = siteWords.filter(word => normalizedModel.includes(word))
    if (matchedWords.length > 0) {
      // Score based on percentage of words matched
      score += Math.round((matchedWords.length / siteWords.length) * 40)
    }
  }

  // Bonus: contains country name
  if (normalizedCountry && normalizedModel.includes(normalizedCountry)) {
    score += 15
  }

  // Bonus: contains archaeology-related keywords
  const hasArchaeologyKeyword = ARCHAEOLOGY_KEYWORDS.some(kw =>
    normalizedModel.includes(kw)
  )
  if (hasArchaeologyKeyword) {
    score += 10
  }

  return Math.min(score, 100)
}

/** Extract country from a location string (last part after comma) */
function extractCountryFromLocation(location: string): string {
  if (!location) return ''
  const parts = location.split(',')
  return parts[parts.length - 1].trim()
}

/**
 * Search for 3D models by site name using Sketchfab API
 */
export async function findModelsForSite(
  siteName: string,
  location: string = '',
  limit: number = 20
): Promise<SketchfabModel[]> {
  // Early return if offline - Sketchfab API requires internet
  if (OfflineFetch.isOffline) {
    return []
  }

  if (!siteName.trim()) {
    return []
  }

  // Check cache first (include location in key since it affects search)
  const cacheKey = `${siteName}|${location}`.toLowerCase().trim()
  const cached = searchCache.get(cacheKey)
  if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
    return cached.models
  }

  // Extract primary name for search and filter
  const primaryName = getPrimaryName(siteName)

  // Extract country from location to improve search relevance
  const country = extractCountryFromLocation(location)

  // Build search query with filters:
  // - categories: cultural-heritage-history
  // - only human-created models (not AI-generated)
  const searchTerm = country ? `${primaryName} ${country}` : primaryName
  const searchQuery = encodeURIComponent(searchTerm)
  const apiUrl = `https://api.sketchfab.com/v3/search?type=models&q=${searchQuery}&sort_by=-likeCount&count=${limit}&categories=cultural-heritage-history&ai_generated=false`

  try {
    const response = await fetch(apiUrl, {
      headers: {
        'Accept': 'application/json'
      }
    })

    // Handle rate limiting (429)
    if (response.status === 429) {
      console.warn('Sketchfab API rate limited')
      return cached?.models || []
    }

    if (!response.ok) {
      console.error('Sketchfab API error:', response.status)
      return []
    }

    const data: ApiResponse = await response.json()

    if (!data.results || data.results.length === 0) {
      // Cache empty results too to avoid repeated requests
      searchCache.set(cacheKey, { models: [], timestamp: Date.now() })
      return []
    }

    console.log(`Found ${data.results.length} 3D models for "${searchTerm}"`)

    // Score and filter models by relevance
    const scoredModels: Array<{ model: SketchfabModel; score: number }> = data.results
      .map(result => {
        // Get best thumbnail (prefer ~640px width)
        const thumbnails = result.thumbnails?.images || []
        const thumbnail = thumbnails.find(t => t.width >= 480 && t.width <= 800)
          || thumbnails.find(t => t.width >= 200)
          || thumbnails[0]

        if (!thumbnail?.url) {
          return null
        }

        const model: SketchfabModel = {
          uid: result.uid,
          name: result.name || 'Untitled',
          thumbnail: thumbnail.url,
          embedUrl: `https://sketchfab.com/models/${result.uid}/embed?autostart=1&ui_controls=1&ui_infos=0&ui_watermark=0`,
          viewerUrl: `https://sketchfab.com/3d-models/${result.uid}`,
          creator: result.user?.displayName || result.user?.username || 'Unknown',
          creatorUrl: result.user?.profileUrl || `https://sketchfab.com/${result.user?.username || ''}`,
          likeCount: result.likeCount || 0,
          viewCount: result.viewCount || 0
        }

        // Calculate relevance score
        const score = scoreModelRelevance(model.name, siteName, primaryName, country)
        return { model, score }
      })
      .filter((item): item is { model: SketchfabModel; score: number } => item !== null)
      // Filter by minimum relevance score
      .filter(item => item.score >= MIN_RELEVANCE_SCORE)
      // Sort by score descending (most relevant first)
      .sort((a, b) => b.score - a.score)

    const models = scoredModels.map(item => item.model)

    if (models.length < data.results.length) {
      console.log(`Filtered to ${models.length} relevant models (min score: ${MIN_RELEVANCE_SCORE})`)
    }

    // Cache results
    searchCache.set(cacheKey, { models, timestamp: Date.now() })

    return models
  } catch (error) {
    console.error('Error searching Sketchfab:', error)
    return cached?.models || []
  }
}

/**
 * Clear the search cache
 */
export function clearSketchfabCache(): void {
  searchCache.clear()
}
