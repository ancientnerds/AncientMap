import { useState, useEffect, useMemo, useCallback } from 'react'
import type { GalleryImage } from '../../ImageGallery'
import type { GalleryTab, UnifiedGalleryItem } from '../types'
import { contentService, type ContentTier } from '../../../services/connectors'
import { fetchSiteImages } from '../../../services/imageService'
import { useTieredFetch } from './useTieredFetch'
import { dedupePhotos, selectCurrentItems } from './galleryUtils'
import type { GalleryHookReturn, SketchfabModelCompat } from './galleryTypes'

interface UseGalleryDataOptions {
  siteId: string
  title: string
  location?: string
  lat: number
  lng: number
  sourceUrl?: string
  isOffline: boolean
  isStandalone?: boolean
}

export function useGalleryData({
  siteId,
  title,
  location,
  lat,
  lng,
  sourceUrl,
  isOffline,
  isStandalone = false,
}: UseGalleryDataOptions): GalleryHookReturn {
  const [activeGalleryTab, setActiveGalleryTab] = useState<GalleryTab>('photos')
  const [isGalleryExpanded, setIsGalleryExpanded] = useState(isStandalone)

  // Internal Wikipedia image fetching
  const [wikiImages, setWikiImages] = useState<GalleryImage[]>([])
  const [isLoadingWikiImages, setIsLoadingWikiImages] = useState(false)

  useEffect(() => {
    if (!siteId || isOffline) return
    setIsLoadingWikiImages(true)
    fetchSiteImages(title, { location, siteId })
      .then(result => {
        setWikiImages(result.wikipedia.map(img => ({
          thumb: img.thumb,
          full: img.full,
          title: img.title,
          photographer: img.author,
          photographerUrl: img.authorUrl,
          wikimediaUrl: img.sourceUrl,
          license: img.license,
          source: 'wikipedia' as const,
        })))
      })
      .catch(() => setWikiImages([]))
      .finally(() => setIsLoadingWikiImages(false))
  }, [siteId])

  const fetchFn = useCallback(
    (tier: ContentTier) => contentService.getContentForSiteTier({
      name: title,
      location: location || undefined,
      lat,
      lon: lng,
      source_url: sourceUrl,
      limit: 200,
    }, tier),
    [title, location, lat, lng, sourceUrl]
  )

  const tiered = useTieredFetch(fetchFn, `${title}-${lat}-${lng}`, !isOffline)

  // Merge Wikipedia images with backend photos (deduped)
  const wikiItems: UnifiedGalleryItem[] = useMemo(() =>
    wikiImages.map((img, i) => ({
      id: `wiki-${i}`,
      thumb: img.thumb,
      full: img.full,
      title: img.title,
      source: 'wikipedia' as const,
      original: img
    })),
    [wikiImages]
  )

  const photoItems = useMemo(
    () => dedupePhotos(wikiItems, tiered.grouped.photos),
    [wikiItems, tiered.grouped.photos]
  )

  const videoItems = tiered.grouped.videos
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

  const heroImage = wikiImages[0] || null
  const heroImageSrc = heroImage?.full || photoItems[0]?.full

  return {
    activeGalleryTab, setActiveGalleryTab,
    isGalleryExpanded, setIsGalleryExpanded,
    photoItems, videoItems, mapItems, sketchfabItems, artifactItems, artworkItems, bookItems, paperItems, mythItems,
    currentItems,
    isLoadingImages: isLoadingWikiImages || tiered.tier1Loading,
    isLoadingVideos: tiered.tier2Loading,
    isLoadingMaps: tiered.tier4Loading,
    isLoadingModels: tiered.tier3Loading,
    isLoadingArtifacts: tiered.tier4Loading,
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
