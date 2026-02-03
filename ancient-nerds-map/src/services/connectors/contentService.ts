/**
 * Unified Content Service
 *
 * Provides a single interface for fetching content from all backend connectors.
 * Replaces scattered frontend services (smithsonianService, sketchfabService, etc.)
 *
 * Usage:
 *   const result = await contentService.searchContent({ query: 'roman temple' })
 *   const siteContent = await contentService.getContentForSite({ name: 'Pompeii', lat: 40.75, lon: 14.48 })
 */

import type {
  ContentItem,
  ContentSearchResponse,
  ContentSearchParams,
  ContentByLocationParams,
  ContentBySiteParams,
  ContentByEmpireParams,
  SourceInfo,
  ContentType,
} from './types'
import { OfflineFetch } from '../OfflineFetch'

// API base URL - uses environment variable or relative path
const API_BASE = import.meta.env.VITE_API_URL || '/api'

/**
 * Content loading priority tiers
 * Tier 1 loads immediately, tiers 2-4 load after a short delay
 */
export const CONTENT_TIERS = {
  tier1: {
    types: ['photo', 'video', 'audio'] as ContentType[],
    timeout: 15,
    label: 'Photos'
  },
  tier2: {
    types: ['model_3d'] as ContentType[],
    timeout: 20,
    label: '3D Models'
  },
  tier3: {
    types: ['map', 'artifact', 'artwork', 'coin'] as ContentType[],
    timeout: 25,
    label: 'Maps & Artifacts'
  },
  tier4: {
    types: ['book', 'manuscript', 'document', 'paper', 'inscription', 'primary_text'] as ContentType[],
    timeout: 30,
    label: 'Texts'
  },
} as const

export type ContentTier = keyof typeof CONTENT_TIERS

// Cache configuration
const CACHE_TTL_MS = 5 * 60 * 1000 // 5 minutes
const cache = new Map<string, { data: ContentSearchResponse; timestamp: number }>()

/**
 * Generate cache key from request parameters
 */
function makeCacheKey(endpoint: string, params: object): string {
  const paramsObj = params as Record<string, unknown>
  const sortedParams = JSON.stringify(paramsObj, Object.keys(paramsObj).sort())
  return `${endpoint}:${sortedParams}`
}

/**
 * Check if cached data is still valid
 */
function getCached(key: string): ContentSearchResponse | null {
  const cached = cache.get(key)
  if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
    return cached.data
  }
  return null
}

/**
 * Store data in cache
 */
function setCache(key: string, data: ContentSearchResponse): void {
  cache.set(key, { data, timestamp: Date.now() })

  // Limit cache size
  if (cache.size > 100) {
    const oldestKey = cache.keys().next().value
    if (oldestKey) cache.delete(oldestKey)
  }
}

/**
 * Make API request with error handling
 */
async function apiRequest<T>(
  endpoint: string,
  params: object = {}
): Promise<T> {
  // Filter out undefined/null values
  const cleanParams = Object.fromEntries(
    Object.entries(params as Record<string, unknown>).filter(([_, v]) => v !== undefined && v !== null)
  )

  // Build URL with query params
  const url = new URL(`${API_BASE}/content${endpoint}`, window.location.origin)
  for (const [key, value] of Object.entries(cleanParams)) {
    if (Array.isArray(value)) {
      value.forEach((v) => url.searchParams.append(key, String(v)))
    } else {
      url.searchParams.set(key, String(value))
    }
  }

  console.log('[contentService] Fetching:', url.toString())
  const response = await fetch(url.toString(), {
    headers: { Accept: 'application/json' },
  })

  console.log('[contentService] Response status:', response.status)

  if (!response.ok) {
    const text = await response.text()
    console.error('[contentService] Error response:', text)
    throw new Error(`API error: ${response.status} ${response.statusText}`)
  }

  const data = await response.json()
  console.log('[contentService] Response data:', data)
  return data
}

/**
 * Unified Content Service
 */
export const contentService = {
  /**
   * Search for content across all connectors
   */
  async searchContent(params: ContentSearchParams): Promise<ContentSearchResponse> {
    if (OfflineFetch.isOffline) {
      return { items: [], total_count: 0, sources_searched: [], sources_failed: [], items_by_source: {}, search_time_ms: 0, cached: false }
    }

    const cacheKey = makeCacheKey('/search', params)
    const cached = getCached(cacheKey)
    if (cached) {
      return { ...cached, cached: true }
    }

    const result = await apiRequest<ContentSearchResponse>('/search', {
      query: params.query,
      content_types: params.contentTypes,
      sources: params.sources,
      limit: params.limit,
      timeout: params.timeout,
    })

    setCache(cacheKey, result)
    return result
  },

  /**
   * Get content near a geographic location
   */
  async getContentByLocation(params: ContentByLocationParams): Promise<ContentSearchResponse> {
    if (OfflineFetch.isOffline) {
      return { items: [], total_count: 0, sources_searched: [], sources_failed: [], items_by_source: {}, search_time_ms: 0, cached: false }
    }

    const cacheKey = makeCacheKey('/by-location', params)
    const cached = getCached(cacheKey)
    if (cached) {
      return { ...cached, cached: true }
    }

    const result = await apiRequest<ContentSearchResponse>('/by-location', {
      lat: params.lat,
      lon: params.lon,
      radius_km: params.radius_km,
      content_types: params.contentTypes,
      sources: params.sources,
      limit: params.limit,
      timeout: params.timeout,
    })

    setCache(cacheKey, result)
    return result
  },

  /**
   * Get content for an archaeological site
   */
  async getContentForSite(params: ContentBySiteParams): Promise<ContentSearchResponse> {
    if (OfflineFetch.isOffline) {
      return { items: [], total_count: 0, sources_searched: [], sources_failed: [], items_by_source: {}, search_time_ms: 0, cached: false }
    }

    const cacheKey = makeCacheKey('/by-site', params)
    const cached = getCached(cacheKey)
    if (cached) {
      return { ...cached, cached: true }
    }

    const result = await apiRequest<ContentSearchResponse>('/by-site', {
      name: params.name,
      location: params.location,
      lat: params.lat,
      lon: params.lon,
      culture: params.culture,
      content_types: params.contentTypes,
      limit: params.limit,
      timeout: params.timeout,
    })

    setCache(cacheKey, result)
    return result
  },

  /**
   * Get content for an archaeological site - tier-specific fetch
   * Uses tier-specific content types and timeout for progressive loading
   */
  async getContentForSiteTier(
    params: Omit<ContentBySiteParams, 'contentTypes' | 'timeout'>,
    tier: ContentTier
  ): Promise<ContentSearchResponse> {
    if (OfflineFetch.isOffline) {
      return { items: [], total_count: 0, sources_searched: [], sources_failed: [], items_by_source: {}, search_time_ms: 0, cached: false }
    }

    const tierConfig = CONTENT_TIERS[tier]
    const tierParams = {
      ...params,
      contentTypes: tierConfig.types,
      timeout: tierConfig.timeout,
    }

    // Cache key includes tier for separate caching
    const cacheKey = makeCacheKey(`/by-site/${tier}`, tierParams)
    const cached = getCached(cacheKey)
    if (cached) {
      return { ...cached, cached: true }
    }

    const result = await apiRequest<ContentSearchResponse>('/by-site', {
      name: params.name,
      location: params.location,
      lat: params.lat,
      lon: params.lon,
      culture: params.culture,
      content_types: tierConfig.types,
      limit: params.limit,
      timeout: tierConfig.timeout,
    })

    setCache(cacheKey, result)
    return result
  },

  /**
   * Get content for an empire/civilization
   */
  async getContentForEmpire(params: ContentByEmpireParams): Promise<ContentSearchResponse> {
    if (OfflineFetch.isOffline) {
      return { items: [], total_count: 0, sources_searched: [], sources_failed: [], items_by_source: {}, search_time_ms: 0, cached: false }
    }

    const cacheKey = makeCacheKey(`/by-empire/${params.empireId}`, params)
    const cached = getCached(cacheKey)
    if (cached) {
      return { ...cached, cached: true }
    }

    const result = await apiRequest<ContentSearchResponse>(`/by-empire/${params.empireId}`, {
      empire_name: params.empireName,
      period_name: params.periodName,
      content_types: params.contentTypes,
      limit: params.limit,
      timeout: params.timeout,
    })

    setCache(cacheKey, result)
    return result
  },

  /**
   * Get content for an empire/civilization - tier-specific fetch
   * Uses tier-specific content types and timeout for progressive loading
   */
  async getContentForEmpireTier(
    params: Omit<ContentByEmpireParams, 'contentTypes' | 'timeout'>,
    tier: ContentTier
  ): Promise<ContentSearchResponse> {
    if (OfflineFetch.isOffline) {
      return { items: [], total_count: 0, sources_searched: [], sources_failed: [], items_by_source: {}, search_time_ms: 0, cached: false }
    }

    const tierConfig = CONTENT_TIERS[tier]
    const tierParams = {
      ...params,
      contentTypes: tierConfig.types,
      timeout: tierConfig.timeout,
    }

    // Cache key includes tier for separate caching
    const cacheKey = makeCacheKey(`/by-empire/${params.empireId}/${tier}`, tierParams)
    const cached = getCached(cacheKey)
    if (cached) {
      return { ...cached, cached: true }
    }

    const result = await apiRequest<ContentSearchResponse>(`/by-empire/${params.empireId}`, {
      empire_name: params.empireName,
      period_name: params.periodName,
      content_types: tierConfig.types,
      limit: params.limit,
      timeout: tierConfig.timeout,
    })

    setCache(cacheKey, result)
    return result
  },

  /**
   * List all available content sources
   */
  async listSources(): Promise<SourceInfo[]> {
    if (OfflineFetch.isOffline) {
      return []
    }

    return apiRequest<SourceInfo[]>('/sources')
  },

  /**
   * List all content types
   */
  async listContentTypes(): Promise<{ id: string; name: string }[]> {
    const result = await apiRequest<{ content_types: { id: string; name: string }[] }>('/types')
    return result.content_types
  },

  /**
   * Clear all cached data
   */
  clearCache(): void {
    cache.clear()
  },

  /**
   * Group content items by their content type
   */
  groupByType(items: ContentItem[]): Map<ContentType, ContentItem[]> {
    const grouped = new Map<ContentType, ContentItem[]>()

    for (const item of items) {
      const type = item.content_type
      if (!grouped.has(type)) {
        grouped.set(type, [])
      }
      grouped.get(type)!.push(item)
    }

    return grouped
  },

  /**
   * Group content items by their source
   */
  groupBySource(items: ContentItem[]): Map<string, ContentItem[]> {
    const grouped = new Map<string, ContentItem[]>()

    for (const item of items) {
      if (!grouped.has(item.source)) {
        grouped.set(item.source, [])
      }
      grouped.get(item.source)!.push(item)
    }

    return grouped
  },
}

export default contentService
