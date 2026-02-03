/**
 * Connectors Module - Unified Content Service
 *
 * This module provides a single interface for fetching content from 50+ external sources.
 * It replaces scattered frontend services with calls to the unified backend API.
 */

export { contentService, default, CONTENT_TIERS } from './contentService'
export type { ContentTier } from './contentService'
export type {
  ContentItem,
  ContentSearchResponse,
  ContentSearchParams,
  ContentByLocationParams,
  ContentBySiteParams,
  ContentByEmpireParams,
  SourceInfo,
  ContentType,
} from './types'
// Content item adapter for mapping backend items to frontend gallery items
export {
  toGalleryItem,
  toLightboxImage,
  toLightboxImages,
  groupByTab,
  getTabForContentType,
  getHeroImage,
  getModelEmbedUrl,
} from './contentItemAdapter'
export type { GroupedGalleryItems } from './contentItemAdapter'
