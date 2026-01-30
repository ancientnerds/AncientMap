import { useState, useEffect, useMemo, useRef } from 'react'
import type { GalleryImage } from '../../ImageGallery'
import { findMapsForLocation, AncientMap } from '../../../services/ancientMapsService'
import { findModelsForSite, SketchfabModel } from '../../../services/sketchfabService'
import type { GalleryTab, UnifiedGalleryItem, Artifact } from '../types'

interface UseGalleryDataOptions {
  title: string
  location?: string
  lat: number
  lng: number
  prefetchedImages?: { wiki: GalleryImage[] } | null
  isOffline: boolean
  isLoadingImages?: boolean
}

interface UseGalleryDataReturn {
  // Active tab
  activeGalleryTab: GalleryTab
  setActiveGalleryTab: (tab: GalleryTab) => void

  // Expansion state
  isGalleryExpanded: boolean
  setIsGalleryExpanded: (expanded: boolean) => void

  // Items by tab
  photoItems: UnifiedGalleryItem[]
  mapItems: UnifiedGalleryItem[]
  sketchfabItems: UnifiedGalleryItem[]
  artifactItems: UnifiedGalleryItem[]
  artworkItems: UnifiedGalleryItem[]
  textItems: UnifiedGalleryItem[]
  mythItems: UnifiedGalleryItem[]

  // Current tab items
  currentItems: UnifiedGalleryItem[]

  // Loading states
  isLoadingImages: boolean
  ancientMapsLoading: boolean
  sketchfabLoading: boolean
  artifactsLoading: boolean
  isLoading: boolean

  // Raw data for external use
  ancientMaps: AncientMap[]
  sketchfabModels: SketchfabModel[]
  artifacts: Artifact[]

  // Hero image
  heroImage: GalleryImage | null
  heroImageSrc: string | undefined
}

export function useGalleryData({
  title,
  location,
  lat,
  lng,
  prefetchedImages,
  isOffline,
  isLoadingImages = false
}: UseGalleryDataOptions): UseGalleryDataReturn {
  const [activeGalleryTab, setActiveGalleryTab] = useState<GalleryTab>('photos')
  const [isGalleryExpanded, setIsGalleryExpanded] = useState(false)

  // Maps & Artifacts - lazy loaded after images
  const [ancientMaps, setAncientMaps] = useState<AncientMap[]>([])
  const [ancientMapsLoading, setAncientMapsLoading] = useState(false)
  const [artifacts] = useState<Artifact[]>([])
  const [artifactsLoading] = useState(false)

  // Sketchfab 3D models - lazy loaded after maps
  const [sketchfabModels, setSketchfabModels] = useState<SketchfabModel[]>([])
  const [sketchfabLoading, setSketchfabLoading] = useState(false)

  // Track if we've already fetched for this site (prevents re-fetching loops)
  const mapsFetchedRef = useRef<string | null>(null)
  const sketchfabFetchedRef = useRef<string | null>(null)

  // Load priority: hero image -> popup opens -> google map -> wiki -> 3D -> maps
  // Maps load after a delay to prioritize images and 3D
  useEffect(() => {
    const siteKey = `${title}-${lat}-${lng}`

    // Skip if already fetched for this site
    if (mapsFetchedRef.current === siteKey) return

    setAncientMapsLoading(true)
    const timer = setTimeout(() => {
      mapsFetchedRef.current = siteKey
      findMapsForLocation(lat, lng, title, location || '')
        .then(setAncientMaps)
        .catch((err) => {
          console.warn('Failed to load ancient maps:', err)
          setAncientMaps([])
        })
        .finally(() => setAncientMapsLoading(false))
    }, 1500) // 1.5s delay after popup opens (after 3D models)

    return () => clearTimeout(timer)
  }, [lat, lng, title, location])

  // Sketchfab 3D models load after photos (1s delay)
  useEffect(() => {
    const siteKey = title

    // Skip if already fetched for this site or offline
    if (sketchfabFetchedRef.current === siteKey || isOffline) return

    setSketchfabLoading(true)
    const timer = setTimeout(() => {
      sketchfabFetchedRef.current = siteKey
      findModelsForSite(title, location || '')
        .then(setSketchfabModels)
        .catch((err) => {
          console.warn('Failed to load 3D models:', err)
          setSketchfabModels([])
        })
        .finally(() => setSketchfabLoading(false))
    }, 1000) // 1s delay after popup opens

    return () => clearTimeout(timer)
  }, [title, location, isOffline])

  // Convert all data to unified gallery items
  const photoItems: UnifiedGalleryItem[] = useMemo(() => {
    const items: UnifiedGalleryItem[] = []
    prefetchedImages?.wiki?.forEach((img, i) => {
      items.push({
        id: `wiki-${i}`,
        thumb: img.thumb,
        full: img.full,
        title: img.title,
        source: 'wikipedia',
        original: img
      })
    })
    return items
  }, [prefetchedImages])

  const mapItems: UnifiedGalleryItem[] = useMemo(() =>
    ancientMaps.map(m => ({
      id: m.id,
      thumb: m.thumbnail,
      full: m.fullImage,
      title: m.title,
      date: m.date || undefined,
      source: 'map' as const,
      original: m
    })), [ancientMaps])

  const artifactItems: UnifiedGalleryItem[] = useMemo(() =>
    artifacts.map(a => ({
      id: String(a.id),
      thumb: a.thumbnail,
      full: a.fullImage,
      title: a.title,
      date: a.date || undefined,
      source: 'artifact' as const,
      original: a
    })), [artifacts])

  const sketchfabItems: UnifiedGalleryItem[] = useMemo(() =>
    sketchfabModels.map(m => ({
      id: m.uid,
      thumb: m.thumbnail,
      full: m.thumbnail, // Not used for 3D models
      title: m.name,
      source: 'sketchfab' as const,
      original: m
    })), [sketchfabModels])

  // Placeholder tabs - empty for now
  const artworkItems: UnifiedGalleryItem[] = []
  const textItems: UnifiedGalleryItem[] = []
  const mythItems: UnifiedGalleryItem[] = []

  // Get current tab items
  const currentItems = activeGalleryTab === 'photos' ? photoItems
    : activeGalleryTab === 'maps' ? mapItems
    : activeGalleryTab === '3dmodels' ? sketchfabItems
    : activeGalleryTab === 'artifacts' ? artifactItems
    : activeGalleryTab === 'artworks' ? artworkItems
    : activeGalleryTab === 'texts' ? textItems
    : mythItems

  const isLoading = activeGalleryTab === 'maps' ? ancientMapsLoading
    : activeGalleryTab === '3dmodels' ? sketchfabLoading
    : activeGalleryTab === 'artifacts' ? artifactsLoading
    : false

  // Hero image
  const heroImage = prefetchedImages?.wiki[0] || null
  const heroImageSrc = heroImage?.full

  return {
    // Active tab
    activeGalleryTab,
    setActiveGalleryTab,

    // Expansion state
    isGalleryExpanded,
    setIsGalleryExpanded,

    // Items by tab
    photoItems,
    mapItems,
    sketchfabItems,
    artifactItems,
    artworkItems,
    textItems,
    mythItems,

    // Current tab items
    currentItems,

    // Loading states
    isLoadingImages,
    ancientMapsLoading,
    sketchfabLoading,
    artifactsLoading,
    isLoading,

    // Raw data for external use
    ancientMaps,
    sketchfabModels,
    artifacts,

    // Hero image
    heroImage,
    heroImageSrc
  }
}
