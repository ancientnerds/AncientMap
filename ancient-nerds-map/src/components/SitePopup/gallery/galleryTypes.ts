import type { GalleryTab, UnifiedGalleryItem } from '../types'

export interface HeroImage {
  id?: string
  thumb: string
  full: string
  title?: string
  photographer?: string
  photographerUrl?: string
  wikimediaUrl?: string
  license?: string
  source?: string
}

export interface SketchfabModelCompat {
  uid: string
  name: string
  thumbnail: string
  embedUrl: string
}

export interface GalleryHookReturn {
  // Tab state
  activeGalleryTab: GalleryTab
  setActiveGalleryTab: (tab: GalleryTab) => void
  isGalleryExpanded: boolean
  setIsGalleryExpanded: (expanded: boolean) => void

  // Items by tab (unused tabs = [])
  photoItems: UnifiedGalleryItem[]
  mapItems: UnifiedGalleryItem[]
  sketchfabItems: UnifiedGalleryItem[]
  artifactItems: UnifiedGalleryItem[]
  artworkItems: UnifiedGalleryItem[]
  bookItems: UnifiedGalleryItem[]
  paperItems: UnifiedGalleryItem[]
  mythItems: UnifiedGalleryItem[]
  currentItems: UnifiedGalleryItem[]

  // Loading states (names match GalleryTabs props directly)
  isLoadingImages: boolean
  isLoadingMaps: boolean
  isLoadingModels: boolean
  isLoadingArtifacts: boolean
  isLoadingBooks: boolean
  isLoadingPapers: boolean
  isLoading: boolean

  // Hero
  heroImage: HeroImage | null
  heroImageSrc: string | undefined

  // Compat for ModelViewer
  sketchfabModels: SketchfabModelCompat[]

  // Connector status metadata
  sourcesSearched: string[]
  sourcesFailed: string[]
  itemsBySource: Record<string, number>
  searchTimeMs: number
}
