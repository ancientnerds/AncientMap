import { useState, useMemo, useCallback } from 'react'
import type { GalleryImage } from '../../ImageGallery'
import type { GalleryTab, UnifiedGalleryItem } from '../types'
import { contentService, type ContentTier } from '../../../services/connectors'
import { useTieredFetch } from './useTieredFetch'
import { dedupePhotos, selectCurrentItems } from './galleryUtils'
import type { GalleryHookReturn, SketchfabModelCompat } from './galleryTypes'

interface UseGalleryDataOptions {
  title: string
  location?: string
  lat: number
  lng: number
  prefetchedImages?: { wiki: GalleryImage[] } | null
  isOffline: boolean
  isLoadingImages?: boolean
}

export function useGalleryData({
  title,
  location,
  lat,
  lng,
  prefetchedImages,
  isOffline,
  isLoadingImages = false
}: UseGalleryDataOptions): GalleryHookReturn {
  const [activeGalleryTab, setActiveGalleryTab] = useState<GalleryTab>('photos')
  const [isGalleryExpanded, setIsGalleryExpanded] = useState(false)

  const fetchFn = useCallback(
    (tier: ContentTier) => contentService.getContentForSiteTier({
      name: title,
      location: location || undefined,
      lat,
      lon: lng,
      limit: 100,
    }, tier),
    [title, location, lat, lng]
  )

  const tiered = useTieredFetch(fetchFn, `${title}-${lat}-${lng}`, !isOffline)

  // Merge prefetched Wikipedia images with backend photos (deduped)
  const wikiItems: UnifiedGalleryItem[] = useMemo(() =>
    (prefetchedImages?.wiki || []).map((img, i) => ({
      id: `wiki-${i}`,
      thumb: img.thumb,
      full: img.full,
      title: img.title,
      source: 'wikipedia' as const,
      original: img
    })),
    [prefetchedImages]
  )

  const photoItems = useMemo(
    () => dedupePhotos(wikiItems, tiered.grouped.photos),
    [wikiItems, tiered.grouped.photos]
  )

  const mapItems = tiered.grouped.maps
  const sketchfabItems = tiered.grouped['3dmodels']
  const artifactItems = tiered.grouped.artifacts
  const artworkItems = tiered.grouped.artworks
  const bookItems = tiered.grouped.books
  const paperItems = tiered.grouped.papers
  const mythItems = tiered.grouped.myths

  const allItems = { ...tiered.grouped, photos: photoItems }
  const currentItems = selectCurrentItems(activeGalleryTab, allItems)

  // Legacy compat: ModelViewer needs this shape
  const sketchfabModels: SketchfabModelCompat[] = useMemo(() =>
    sketchfabItems.map(item => {
      const orig = item.original as Record<string, unknown>
      return {
        uid: item.id,
        name: item.title || '',
        thumbnail: item.thumb,
        embedUrl: (orig?.embed_url as string) || (orig?.embedUrl as string) || `https://sketchfab.com/models/${item.id}/embed`
      }
    }),
    [sketchfabItems]
  )

  const heroImage = prefetchedImages?.wiki?.[0] || null
  const heroImageSrc = heroImage?.full || photoItems[0]?.full

  return {
    activeGalleryTab, setActiveGalleryTab,
    isGalleryExpanded, setIsGalleryExpanded,
    photoItems, mapItems, sketchfabItems, artifactItems, artworkItems, bookItems, paperItems, mythItems,
    currentItems,
    isLoadingImages: isLoadingImages || tiered.tier1Loading,
    isLoadingMaps: tiered.tier3Loading,
    isLoadingModels: tiered.tier2Loading,
    isLoadingArtifacts: tiered.tier3Loading,
    isLoadingBooks: tiered.tier4Loading,
    isLoadingPapers: tiered.tier4Loading,
    isLoading: tiered.isLoading,
    heroImage: heroImage ? {
      thumb: heroImage.thumb,
      full: heroImage.full,
      title: heroImage.title,
      photographer: heroImage.photographer,
      wikimediaUrl: heroImage.wikimediaUrl,
      license: heroImage.license,
    } : null,
    heroImageSrc,
    sketchfabModels,
    sourcesSearched: tiered.sourcesSearched,
    sourcesFailed: tiered.sourcesFailed,
    itemsBySource: tiered.itemsBySource,
    searchTimeMs: tiered.searchTimeMs,
  }
}
