import { useState, useEffect, useMemo } from 'react'
import { getEmpireImages, WikidataImage } from '../../../services/wikipediaService'
import { searchHistoricalMaps, WikimediaMap } from '../../../services/wikimediaMapsService'
import { searchSmithsonian, SmithsonianArtifact, SmithsonianText } from '../../../services/smithsonianService'
import type { GalleryTab, UnifiedGalleryItem } from '../types'

// Module-level cache: periodName -> images
const imageCache = new Map<string, WikidataImage[]>()

interface UseEmpireGalleryDataOptions {
  empireId?: string       // Empire ID (e.g., "roman") - kept for potential future use
  empireName: string      // Empire name (e.g., "Roman Empire")
  periodName?: string | null  // Period-specific name (e.g., "Roman Principate")
  isOffline: boolean
}

interface UseEmpireGalleryDataReturn {
  activeGalleryTab: GalleryTab
  setActiveGalleryTab: (tab: GalleryTab) => void
  isGalleryExpanded: boolean
  setIsGalleryExpanded: (expanded: boolean) => void
  photoItems: UnifiedGalleryItem[]
  mapItems: UnifiedGalleryItem[]
  artifactItems: UnifiedGalleryItem[]
  textItems: UnifiedGalleryItem[]
  currentItems: UnifiedGalleryItem[]
  isLoadingImages: boolean
  isLoadingMaps: boolean
  isLoadingArtifacts: boolean
  isLoadingTexts: boolean
  isLoading: boolean
  heroImage: WikidataImage | null
  heroImageSrc: string | undefined
  rawImages: WikidataImage[]
  historicalMaps: WikimediaMap[]
  smithsonianArtifacts: SmithsonianArtifact[]
  smithsonianTexts: SmithsonianText[]
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

  // Historical maps state
  const [historicalMaps, setHistoricalMaps] = useState<WikimediaMap[]>([])
  const [isLoadingMaps, setIsLoadingMaps] = useState(false)

  // Smithsonian state
  const [smithsonianArtifacts, setSmithsonianArtifacts] = useState<SmithsonianArtifact[]>([])
  const [smithsonianTexts, setSmithsonianTexts] = useState<SmithsonianText[]>([])
  const [isLoadingSmithsonian, setIsLoadingSmithsonian] = useState(false)

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

  // Search for historical maps dynamically
  useEffect(() => {
    if (!empireName || isOffline) {
      setHistoricalMaps([])
      return
    }

    setIsLoadingMaps(true)

    // Search with period name for specificity, empire name as fallback context
    const searchPeriod = periodName || empireName
    searchHistoricalMaps(searchPeriod, empireName, 15)
      .then((maps) => {
        setHistoricalMaps(maps)
      })
      .catch((err) => {
        console.warn(`Failed to search maps for "${searchPeriod}":`, err)
        setHistoricalMaps([])
      })
      .finally(() => setIsLoadingMaps(false))
  }, [periodName, empireName, isOffline])

  // Search Smithsonian for artifacts and texts
  useEffect(() => {
    if (!empireName || isOffline) {
      setSmithsonianArtifacts([])
      setSmithsonianTexts([])
      return
    }

    setIsLoadingSmithsonian(true)

    // Use empire name for searching (e.g., "Roman", "Egyptian", "Chinese")
    // Extract base empire name without "Empire" suffix for better results
    const searchTerm = empireName.replace(/\s*(Empire|Kingdom|Dynasty|Civilization)$/i, '').trim()

    searchSmithsonian(searchTerm, 15)
      .then(({ artifacts, texts }) => {
        setSmithsonianArtifacts(artifacts)
        setSmithsonianTexts(texts)
      })
      .catch((err) => {
        console.warn(`Failed to search Smithsonian for "${searchTerm}":`, err)
        setSmithsonianArtifacts([])
        setSmithsonianTexts([])
      })
      .finally(() => setIsLoadingSmithsonian(false))
  }, [empireName, isOffline])

  // Convert photos to gallery items
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

  // Convert historical maps to gallery items
  const mapItems: UnifiedGalleryItem[] = useMemo(() => {
    return historicalMaps.map((map) => ({
      id: map.id,
      thumb: map.thumb,
      full: map.full,
      title: map.displayTitle,
      source: 'map' as const,
      original: {
        id: map.id,
        title: map.displayTitle,
        date: null,
        thumbnail: map.thumb,
        fullImage: map.full,
        webUrl: map.wikimediaUrl,
        // Extended fields for lightbox attribution
        description: map.description,
        license: map.license,
        artist: map.artist,
        source: 'wikimedia' as const
      }
    }))
  }, [historicalMaps])

  // Convert Smithsonian artifacts to gallery items
  const artifactItems: UnifiedGalleryItem[] = useMemo(() => {
    return smithsonianArtifacts.map((artifact) => ({
      id: artifact.id,
      thumb: artifact.thumbnail,
      full: artifact.fullImage,
      title: artifact.title,
      date: artifact.date,
      source: 'smithsonian' as const,
      original: artifact
    }))
  }, [smithsonianArtifacts])

  // Convert Smithsonian texts to gallery items (for text tab)
  const textItems: UnifiedGalleryItem[] = useMemo(() => {
    return smithsonianTexts.map((text) => ({
      id: text.id,
      thumb: '', // Texts don't have thumbnails
      full: '',
      title: text.title,
      date: text.date,
      source: 'smithsonian' as const,
      original: text
    }))
  }, [smithsonianTexts])

  // Get current items based on active tab
  const currentItems = useMemo(() => {
    switch (activeGalleryTab) {
      case 'photos':
        return photoItems
      case 'maps':
        return mapItems
      case 'artifacts':
        return artifactItems
      case 'texts':
        return textItems
      default:
        return []
    }
  }, [activeGalleryTab, photoItems, mapItems, artifactItems, textItems])

  // Loading state based on active tab
  const isLoading = useMemo(() => {
    switch (activeGalleryTab) {
      case 'photos':
        return isLoadingImages
      case 'maps':
        return isLoadingMaps
      case 'artifacts':
      case 'texts':
        return isLoadingSmithsonian
      default:
        return false
    }
  }, [activeGalleryTab, isLoadingImages, isLoadingMaps, isLoadingSmithsonian])

  // Hero image is the first image (in document order from Wikipedia)
  const heroImage = images.length > 0 ? images[0] : null
  const heroImageSrc = heroImage?.full

  return {
    activeGalleryTab,
    setActiveGalleryTab,
    isGalleryExpanded,
    setIsGalleryExpanded,
    photoItems,
    mapItems,
    artifactItems,
    textItems,
    currentItems,
    isLoadingImages,
    isLoadingMaps,
    isLoadingArtifacts: isLoadingSmithsonian,
    isLoadingTexts: isLoadingSmithsonian,
    isLoading,
    heroImage,
    heroImageSrc,
    rawImages: images,
    historicalMaps,
    smithsonianArtifacts,
    smithsonianTexts
  }
}
