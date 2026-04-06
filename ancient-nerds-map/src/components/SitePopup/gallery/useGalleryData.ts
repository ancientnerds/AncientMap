import { useState, useEffect, useMemo, useCallback } from 'react'
import type { GalleryImage } from '../../ImageGallery'
import type { GalleryTab, UnifiedGalleryItem } from '../types'
import { contentService, type ContentTier } from '../../../services/connectors'
import { fetchSiteImages } from '../../../services/imageService'
import { config } from '../../../config'
import { useTieredFetch } from './useTieredFetch'
import { useWebcamData } from './useWebcamData'
import { dedupePhotos, selectCurrentItems } from './galleryUtils'
import type { GalleryHookReturn, SketchfabModelCompat } from './galleryTypes'
import type { NewsItemData } from '../../../types/news'

interface UseGalleryDataOptions {
  siteId: string
  title: string
  location?: string
  lat: number
  lng: number
  sourceUrl?: string
  thumbnailUrl?: string
  isOffline: boolean
}

export function useGalleryData({
  siteId,
  title,
  location,
  lat,
  lng,
  sourceUrl,
  thumbnailUrl,
  isOffline,
}: UseGalleryDataOptions): GalleryHookReturn {
  const [activeGalleryTab, setActiveGalleryTab] = useState<GalleryTab>('photos')
  const [isGalleryExpanded, setIsGalleryExpanded] = useState(false)
  const [sketchfabCategoryFilter, setSketchfabCategoryFilter] = useState(false)

  // Internal Wikipedia image fetching
  const [wikiImages, setWikiImages] = useState<GalleryImage[]>([])
  const [isLoadingWikiImages, setIsLoadingWikiImages] = useState(false)

  // Hero image override (set when user picks a new hero via lightbox)
  const [heroImageOverride, setHeroImageOverride] = useState<string | null>(null)

  useEffect(() => {
    if (!siteId || isOffline) return
    setIsLoadingWikiImages(true)
    fetchSiteImages(title, { location, siteId, wikipediaUrl: sourceUrl })
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
  }, [siteId, sourceUrl])

  const fetchFn = useCallback(
    (tier: ContentTier) => contentService.getContentForSiteTier({
      name: title,
      location: location || undefined,
      lat,
      lon: lng,
      source_url: sourceUrl,
      limit: 200,
      sketchfabCategoryFilter,
    }, tier),
    [title, location, lat, lng, sourceUrl, sketchfabCategoryFilter]
  )

  const tiered = useTieredFetch(fetchFn, `${title}-${lat}-${lng}-${sketchfabCategoryFilter}`, !isOffline)

  const { webcamItems, isLoadingWebcams } = useWebcamData({ lat, lng, isOffline })

  // Stories: fetch news items linked to this site
  const [storiesItems, setStoriesItems] = useState<NewsItemData[]>([])
  const [isLoadingStories, setIsLoadingStories] = useState(false)

  useEffect(() => {
    if (!siteId || isOffline) return
    setIsLoadingStories(true)
    const controller = new AbortController()
    fetch(`${config.api.baseUrl}/news/feed?site_id=${encodeURIComponent(siteId)}&page_size=20&sort=significance`, {
      signal: controller.signal,
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.items) setStoriesItems(data.items) })
      .catch(() => {})
      .finally(() => setIsLoadingStories(false))
    return () => controller.abort()
  }, [siteId, isOffline])

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

  const allItems = { ...tiered.grouped, photos: photoItems, webcams: webcamItems }
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

  const wikiHero = wikiImages[0] || null
  // Curated thumbnail (card image) takes priority to avoid hero swap on popup open
  // heroImageOverride takes top priority (user just set a new hero via lightbox)
  const heroImageSrc = heroImageOverride || thumbnailUrl || wikiHero?.full || photoItems[0]?.full
  // Only attach wiki metadata when the displayed hero is actually from wiki images
  const heroImage = (!thumbnailUrl && wikiHero) ? {
    thumb: wikiHero.thumb,
    full: wikiHero.full,
    title: wikiHero.title,
    photographer: wikiHero.photographer,
    wikimediaUrl: wikiHero.wikimediaUrl,
    license: wikiHero.license,
  } : null

  return {
    activeGalleryTab, setActiveGalleryTab,
    isGalleryExpanded, setIsGalleryExpanded,
    sketchfabCategoryFilter, setSketchfabCategoryFilter,
    photoItems, videoItems, mapItems, sketchfabItems, artifactItems, artworkItems, bookItems, paperItems, mythItems, webcamItems, storiesItems,
    currentItems,
    isLoadingImages: isLoadingWikiImages || tiered.tier1Loading,
    isLoadingVideos: tiered.tier2Loading,
    isLoadingMaps: tiered.tier4Loading,
    isLoadingModels: tiered.tier3Loading,
    isLoadingArtifacts: tiered.tier4Loading,
    isLoadingBooks: tiered.tier4Loading,
    isLoadingPapers: tiered.tier4Loading,
    isLoadingWebcams,
    isLoadingStories,
    isLoading: tiered.isLoading,
    heroImage,
    heroImageSrc,
    setHeroImageSrc: setHeroImageOverride,
    sketchfabModels,
    sourcesSearched: tiered.sourcesSearched,
    sourcesFailed: tiered.sourcesFailed,
    itemsBySource: tiered.itemsBySource,
    searchTimeMs: tiered.searchTimeMs,
  }
}
