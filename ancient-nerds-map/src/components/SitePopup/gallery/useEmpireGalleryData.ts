import { useState, useEffect, useMemo } from 'react'
import { getEmpireImages, WikidataImage } from '../../../services/wikipediaService'
import type { GalleryTab, UnifiedGalleryItem } from '../types'

// Module-level cache: periodName -> images
const imageCache = new Map<string, WikidataImage[]>()

interface UseEmpireGalleryDataOptions {
  empireName: string      // Fallback name (e.g., "Roman Empire")
  periodName?: string | null  // Period-specific name (e.g., "Roman Principate")
  isOffline: boolean
}

interface UseEmpireGalleryDataReturn {
  activeGalleryTab: GalleryTab
  setActiveGalleryTab: (tab: GalleryTab) => void
  isGalleryExpanded: boolean
  setIsGalleryExpanded: (expanded: boolean) => void
  photoItems: UnifiedGalleryItem[]
  currentItems: UnifiedGalleryItem[]
  isLoadingImages: boolean
  isLoading: boolean
  heroImage: WikidataImage | null
  heroImageSrc: string | undefined
  rawImages: WikidataImage[]
}

export function useEmpireGalleryData({
  empireName,
  periodName,
  isOffline
}: UseEmpireGalleryDataOptions): UseEmpireGalleryDataReturn {
  const [activeGalleryTab, setActiveGalleryTab] = useState<GalleryTab>('photos')
  const [isGalleryExpanded, setIsGalleryExpanded] = useState(false)
  const [images, setImages] = useState<WikidataImage[]>([])
  const [isLoadingImages, setIsLoadingImages] = useState(false)

  // The name to search for (period name or fall back to empire name)
  const searchName = periodName || empireName
  const cacheKey = searchName

  // Fetch images for the current period/empire
  useEffect(() => {
    if (!searchName || isOffline) return

    // Check cache first
    const cached = imageCache.get(cacheKey)
    if (cached) {
      setImages(cached)
      return
    }

    setIsLoadingImages(true)

    // Fetch images: try periodName first, fall back to empireName
    getEmpireImages(searchName, empireName)
      .then((fetchedImages) => {
        imageCache.set(cacheKey, fetchedImages)
        setImages(fetchedImages)
      })
      .catch((err) => {
        console.warn(`Failed to fetch images for "${searchName}":`, err)
        setImages([])
      })
      .finally(() => setIsLoadingImages(false))
  }, [searchName, empireName, cacheKey, isOffline])

  // Convert to gallery items
  const photoItems: UnifiedGalleryItem[] = useMemo(() => {
    return images.map((img, i) => ({
      id: img.id || `empire-img-${i}`,
      thumb: img.thumb,
      full: img.full,
      title: img.title,
      source: 'wikipedia' as const,
      original: {
        thumb: img.thumb,
        full: img.full,
        title: img.title,
        photographer: img.photographer,
        photographerUrl: img.photographerUrl,
        wikimediaUrl: img.wikimediaUrl,
        license: img.license,
        source: 'wikipedia' as const
      }
    }))
  }, [images])

  const currentItems = activeGalleryTab === 'photos' ? photoItems : []
  const isLoading = activeGalleryTab === 'photos' ? isLoadingImages : false

  // Hero image is the first image (in document order from Wikipedia)
  const heroImage = images.length > 0 ? images[0] : null
  const heroImageSrc = heroImage?.full

  return {
    activeGalleryTab,
    setActiveGalleryTab,
    isGalleryExpanded,
    setIsGalleryExpanded,
    photoItems,
    currentItems,
    isLoadingImages,
    isLoading,
    heroImage,
    heroImageSrc,
    rawImages: images
  }
}
