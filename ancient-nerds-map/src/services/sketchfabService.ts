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

// Extract search-friendly name from site title
// "The Great Pyramid of Giza" -> "Great Pyramid Giza"
function getPrimaryName(name: string): string {
  // 1. Remove suffixes after -, (, ,
  let result = name.split(/\s*[-,(]\s*/)[0].trim()

  // 2. Remove leading articles
  result = result.replace(/^(The|A|An)\s+/i, '')

  // 3. Remove filler words (prepositions/articles in middle)
  result = result.replace(/\b(of|the|at|in|on)\b/gi, ' ')

  // 4. Clean up extra spaces
  result = result.replace(/\s+/g, ' ').trim()

  return result || name
}

/**
 * Search for 3D models by site name using Sketchfab API
 */
export async function findModelsForSite(
  siteName: string,
  limit: number = 20
): Promise<SketchfabModel[]> {
  // Early return if offline - Sketchfab API requires internet
  if (OfflineFetch.isOffline) {
    return []
  }

  if (!siteName.trim()) {
    return []
  }

  // Check cache first
  const cacheKey = siteName.toLowerCase().trim()
  const cached = searchCache.get(cacheKey)
  if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
    return cached.models
  }

  // Extract primary name for search and filter
  const primaryName = getPrimaryName(siteName)

  // Build search query with filters:
  // - categories: cultural-heritage-history
  // - only human-created models (not AI-generated)
  const searchQuery = encodeURIComponent(primaryName)
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

    console.log(`Found ${data.results.length} 3D models for "${siteName}"`)

    // Normalize primary name for matching (lowercase, remove diacritics)
    const normalizedPrimaryName = primaryName.toLowerCase()
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '') // Remove diacritics

    const models: SketchfabModel[] = data.results
      .map(result => {
        // Get best thumbnail (prefer ~640px width)
        const thumbnails = result.thumbnails?.images || []
        const thumbnail = thumbnails.find(t => t.width >= 480 && t.width <= 800)
          || thumbnails.find(t => t.width >= 200)
          || thumbnails[0]

        if (!thumbnail?.url) {
          return null
        }

        return {
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
      })
      .filter((model): model is SketchfabModel => model !== null)
      // Only include models where the name contains the primary site name
      .filter(model => {
        // Normalize model name the same way: remove filler words, diacritics
        const normalizedModelName = model.name.toLowerCase()
          .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
          .replace(/\b(of|the|at|in|on)\b/gi, ' ')
          .replace(/\s+/g, ' ').trim()
        return normalizedModelName.includes(normalizedPrimaryName)
      })

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
