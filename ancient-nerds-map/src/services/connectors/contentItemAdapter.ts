/**
 * Content Item Adapter
 *
 * Maps backend ContentItem to frontend UnifiedGalleryItem and groups items by gallery tab.
 * This adapter bridges the unified backend connector system with the frontend gallery components.
 */

import type { ContentItem, ContentType } from './types'
import type { UnifiedGalleryItem, GalleryTab } from '../../components/SitePopup/types'
import type { LightboxImage } from '../../components/ImageLightbox'

/**
 * Mapping from content types to gallery tabs
 */
const CONTENT_TYPE_TO_TAB: Record<ContentType, GalleryTab> = {
  photo: 'photos',
  artwork: 'artworks',
  map: 'maps',
  model_3d: '3dmodels',
  artifact: 'artifacts',
  coin: 'artifacts',
  inscription: 'artifacts',
  primary_text: 'books',
  manuscript: 'books',
  book: 'books',
  paper: 'papers',
  document: 'papers',
  video: 'photos',
  audio: 'photos',
  vocabulary_term: 'artifacts',
  place: 'artifacts',
  period: 'artifacts',
}

/**
 * Mapping from connector source ID to LightboxImage sourceType
 */
const SOURCE_TO_LIGHTBOX_TYPE: Record<string, LightboxImage['sourceType']> = {
  wikipedia: 'wikimedia',
  wikimedia_commons: 'wikimedia',
  wikimedia: 'wikimedia',
  david_rumsey: 'david-rumsey',
  met_museum: 'met-museum',
  metropolitan_museum: 'met-museum',
  smithsonian: 'smithsonian',
  smithsonian_open_access: 'smithsonian',
  europeana: 'europeana',
  loc: 'loc',
  library_of_congress: 'loc',
  british_museum: 'british-museum',
  sketchfab: 'sketchfab',
}

/**
 * Convert a backend ContentItem to a frontend UnifiedGalleryItem
 */
export function toGalleryItem(item: ContentItem): UnifiedGalleryItem {
  return {
    id: item.id,
    thumb: item.thumbnail_url || '',
    full: item.media_url || item.thumbnail_url || '',
    title: item.title,
    date: item.date || undefined,
    source: item.source as UnifiedGalleryItem['source'],
    original: {
      // Store the full ContentItem as original for lightbox conversion
      ...item,
      // Map fields for compatibility with existing lightbox logic
      thumbnail: item.thumbnail_url || '',
      fullImage: item.media_url || item.thumbnail_url || '',
      sourceUrl: item.url,
      webUrl: item.url,
      embedUrl: item.embed_url,
      museum: item.museum,
      license: item.license,
      artist: item.creator,
      artistUrl: item.creator_url,
      photographer: item.creator,
      photographerUrl: item.creator_url,
      wikimediaUrl: item.url,
      description: item.description,
    }
  }
}

/**
 * Convert a backend ContentItem to a LightboxImage for display in the lightbox
 */
export function toLightboxImage(item: ContentItem): LightboxImage {
  const sourceType = SOURCE_TO_LIGHTBOX_TYPE[item.source] || item.source as LightboxImage['sourceType']

  return {
    src: item.media_url || item.thumbnail_url || '',
    title: item.title,
    photographer: item.creator || item.museum,
    photographerUrl: item.creator_url,
    sourceType,
    sourceUrl: item.url,
    license: item.license,
  }
}

/**
 * Get the gallery tab for a content type
 */
export function getTabForContentType(contentType: ContentType): GalleryTab {
  return CONTENT_TYPE_TO_TAB[contentType] || 'photos'
}

/**
 * Result of grouping items by gallery tab
 */
export interface GroupedGalleryItems {
  photos: UnifiedGalleryItem[]
  maps: UnifiedGalleryItem[]
  '3dmodels': UnifiedGalleryItem[]
  artifacts: UnifiedGalleryItem[]
  artworks: UnifiedGalleryItem[]
  books: UnifiedGalleryItem[]
  papers: UnifiedGalleryItem[]
  myths: UnifiedGalleryItem[]
}

/**
 * Group ContentItems by their gallery tab
 */
export function groupByTab(items: ContentItem[]): GroupedGalleryItems {
  const grouped: GroupedGalleryItems = {
    photos: [],
    maps: [],
    '3dmodels': [],
    artifacts: [],
    artworks: [],
    books: [],
    papers: [],
    myths: [], // Custom content, not from connectors
  }

  for (const item of items) {
    const tab = getTabForContentType(item.content_type)
    const galleryItem = toGalleryItem(item)
    grouped[tab].push(galleryItem)
  }

  return grouped
}

/**
 * Convert an array of UnifiedGalleryItems (with ContentItem originals) to LightboxImages
 */
export function toLightboxImages(items: UnifiedGalleryItem[]): LightboxImage[] {
  return items.map(item => {
    const original = item.original as Record<string, unknown>
    // Check if original has ContentItem structure (has content_type)
    if (original && 'content_type' in original) {
      return toLightboxImage(original as unknown as ContentItem)
    }
    // Fallback for legacy items
    return {
      src: item.full,
      title: item.title,
      photographer: original?.photographer as string || undefined,
      photographerUrl: original?.photographerUrl as string || undefined,
      sourceType: SOURCE_TO_LIGHTBOX_TYPE[item.source] || item.source as LightboxImage['sourceType'],
      sourceUrl: original?.sourceUrl as string ||
                 original?.webUrl as string ||
                 original?.wikimediaUrl as string,
      license: original?.license as string || undefined,
    }
  })
}

/**
 * Get the embed URL for a 3D model item
 */
export function getModelEmbedUrl(item: UnifiedGalleryItem): string | undefined {
  const original = item.original as Record<string, unknown>
  if (original && 'embed_url' in original) {
    return original.embed_url as string
  }
  // Fallback for legacy Sketchfab items
  if (original?.uid) {
    return `https://sketchfab.com/models/${original.uid}/embed`
  }
  return undefined
}

/**
 * Extract hero image from grouped items
 * Prefers photos, falls back to artworks, then maps
 */
export function getHeroImage(grouped: GroupedGalleryItems): UnifiedGalleryItem | null {
  if (grouped.photos.length > 0) return grouped.photos[0]
  if (grouped.artworks.length > 0) return grouped.artworks[0]
  if (grouped.maps.length > 0) return grouped.maps[0]
  return null
}
