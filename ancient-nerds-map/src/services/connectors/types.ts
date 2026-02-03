/**
 * Content types and interfaces for the unified Connectors service.
 *
 * These types match the backend API responses from /api/content endpoints.
 */

/** Content type enum matching backend ContentType */
export type ContentType =
  | 'photo'
  | 'artwork'
  | 'map'
  | 'model_3d'
  | 'artifact'
  | 'coin'
  | 'inscription'
  | 'primary_text'
  | 'manuscript'
  | 'book'
  | 'paper'
  | 'document'
  | 'video'
  | 'audio'
  | 'vocabulary_term'
  | 'place'
  | 'period'

/** Single content item from any connector */
export interface ContentItem {
  id: string
  source: string
  content_type: ContentType
  title: string
  url: string
  thumbnail_url?: string
  media_url?: string
  embed_url?: string
  creator?: string
  creator_url?: string
  date?: string
  period?: string
  culture?: string
  description?: string
  license?: string
  attribution?: string
  museum?: string
  relevance_score: number
}

/** Response from content search endpoints */
export interface ContentSearchResponse {
  items: ContentItem[]
  total_count: number
  sources_searched: string[]
  sources_failed: string[]
  items_by_source: Record<string, number>
  search_time_ms: number
  cached: boolean
}

/** Information about a content source/connector */
export interface SourceInfo {
  connector_id: string
  connector_name: string
  description?: string
  content_types: ContentType[]
  protocol?: string
  requires_auth: boolean
  rate_limit: number
  enabled: boolean
  license?: string
  attribution?: string
}

/** Parameters for searching content */
export interface ContentSearchParams {
  query: string
  contentTypes?: ContentType[]
  sources?: string[]
  limit?: number
  timeout?: number
}

/** Parameters for getting content by location */
export interface ContentByLocationParams {
  lat: number
  lon: number
  radius_km?: number
  contentTypes?: ContentType[]
  sources?: string[]
  limit?: number
  timeout?: number
}

/** Parameters for getting content by site */
export interface ContentBySiteParams {
  name: string
  location?: string
  lat?: number
  lon?: number
  culture?: string
  contentTypes?: ContentType[]
  limit?: number
  timeout?: number
}

/** Parameters for getting content by empire */
export interface ContentByEmpireParams {
  empireId: string
  empireName?: string
  periodName?: string
  contentTypes?: ContentType[]
  limit?: number
  timeout?: number
}

