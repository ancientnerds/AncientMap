import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import type { GalleryTab, UnifiedGalleryItem } from '../types'
import { contentService, type ContentTier } from '../../../services/connectors'
import { fetchSiteImages, type ImageResult } from '../../../services/imageService'
import { useTieredFetch } from './useTieredFetch'
import { dedupePhotos, selectCurrentItems } from './galleryUtils'
import type { GalleryHookReturn, HeroImage, SketchfabModelCompat } from './galleryTypes'

interface UseEmpireGalleryDataOptions {
  empireId?: string
  empireName: string
  periodName?: string | null
  wikiThumbnail?: string | null
  isOffline: boolean
}

export function useEmpireGalleryData({
  empireId,
  empireName,
  periodName,
  wikiThumbnail,
  isOffline
}: UseEmpireGalleryDataOptions): GalleryHookReturn {
  const [activeGalleryTab, setActiveGalleryTab] = useState<GalleryTab>('photos')
  const [isGalleryExpanded, setIsGalleryExpanded] = useState(false)

  // Wikipedia article images (fetched via fast REST API)
  const [wikiImages, setWikiImages] = useState<ImageResult[]>([])
  const [wikiLoading, setWikiLoading] = useState(false)
  const wikiFetchedRef = useRef<string | null>(null)

  // Wikipedia images - fetch immediately via REST API (~400ms)
  useEffect(() => {
    if (!empireName || isOffline) { setWikiImages([]); return }

    const wikiKey = empireName
    if (wikiFetchedRef.current === wikiKey) return
    wikiFetchedRef.current = wikiKey
    setWikiLoading(true)

    fetchSiteImages(empireName)
      .then(result => {
        if (result.wikipedia.length > 0) {
          setWikiImages(result.wikipedia)
          return null
        }
        if (periodName && periodName !== empireName) {
          return fetchSiteImages(periodName)
        }
        return null
      })
      .then(fallback => {
        if (fallback?.wikipedia?.length) setWikiImages(fallback.wikipedia)
      })
      .catch(() => setWikiImages([]))
      .finally(() => setWikiLoading(false))
  }, [empireName, periodName, isOffline])

  // Backend connectors - all tiers in parallel via shared hook
  const searchKey = `${empireId}-${periodName || empireName}`

  const fetchFn = useCallback(
    (tier: ContentTier) => contentService.getContentForEmpireTier({
      empireId: empireId!, empireName, periodName: periodName || undefined, limit: 100,
    }, tier),
    [empireId, empireName, periodName]
  )

  const tiered = useTieredFetch(fetchFn, searchKey, !!empireId && !!empireName && !isOffline)

  // Wikipedia images as UnifiedGalleryItems
  const wikiGallery: UnifiedGalleryItem[] = useMemo(() =>
    wikiImages.map((img, i) => ({
      id: `wiki-${i}`,
      thumb: img.thumb,
      full: img.full,
      title: img.title,
      source: 'wikipedia' as const,
      original: { photographer: img.author, wikimediaUrl: img.sourceUrl, license: img.license }
    })),
    [wikiImages]
  )

  const photoItems = useMemo(
    () => dedupePhotos(wikiGallery, tiered.grouped.photos),
    [wikiGallery, tiered.grouped.photos]
  )

  const mapItems = tiered.grouped.maps
  const sketchfabItems = tiered.grouped['3dmodels']
  const artifactItems = tiered.grouped.artifacts
  const artworkItems = tiered.grouped.artworks
  const bookItems = tiered.grouped.books
  const paperItems = tiered.grouped.papers
  const mythItems = tiered.grouped.myths

  const allItems = { ...tiered.grouped, photos: photoItems }
  const currentItems = useMemo(
    () => selectCurrentItems(activeGalleryTab, allItems),
    [activeGalleryTab, photoItems, mapItems, sketchfabItems, artifactItems, artworkItems, bookItems, paperItems, mythItems]
  )

  const isLoading = wikiLoading || tiered.isLoading

  // Hero: wikiImages → wikiThumbnail → connector photo
  const heroImage: HeroImage | null = useMemo(() => {
    if (wikiImages.length > 0) {
      const first = wikiImages[0]
      return {
        id: 'wiki-0', thumb: first.thumb, full: first.full,
        title: first.title || '', photographer: first.author,
        wikimediaUrl: first.sourceUrl, license: first.license
      }
    }
    if (wikiThumbnail) {
      return { id: 'wiki-summary', thumb: wikiThumbnail, full: wikiThumbnail, title: empireName }
    }
    if (photoItems.length === 0) return null
    const first = photoItems[0]
    const orig = first.original as Record<string, unknown>
    return {
      id: first.id, thumb: first.thumb, full: first.full, title: first.title || '',
      photographer: (orig?.creator as string) || (orig?.photographer as string),
      wikimediaUrl: (orig?.url as string) || (orig?.wikimediaUrl as string),
      license: orig?.license as string
    }
  }, [wikiImages, wikiThumbnail, empireName, photoItems])

  const heroImageSrc = heroImage?.full

  // ModelViewer compat (empires rarely have 3D models but keep the interface consistent)
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

  return {
    activeGalleryTab, setActiveGalleryTab,
    isGalleryExpanded, setIsGalleryExpanded,
    photoItems, mapItems, sketchfabItems, artifactItems, artworkItems, bookItems, paperItems, mythItems,
    currentItems,
    isLoadingImages: wikiLoading || tiered.tier1Loading,
    isLoadingMaps: tiered.tier3Loading,
    isLoadingModels: tiered.tier2Loading,
    isLoadingArtifacts: tiered.tier3Loading,
    isLoadingBooks: tiered.tier4Loading,
    isLoadingPapers: tiered.tier4Loading,
    isLoading,
    heroImage, heroImageSrc,
    sketchfabModels,
    sourcesSearched: tiered.sourcesSearched,
    sourcesFailed: tiered.sourcesFailed,
    itemsBySource: tiered.itemsBySource,
    searchTimeMs: tiered.searchTimeMs,
  }
}
