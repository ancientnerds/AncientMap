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
  videoItems: UnifiedGalleryItem[]
  mapItems: UnifiedGalleryItem[]
  sketchfabItems: UnifiedGalleryItem[]
  artifactItems: UnifiedGalleryItem[]
  bookItems: UnifiedGalleryItem[]
  paperItems: UnifiedGalleryItem[]
  referenceItems: { url: string; title: string; domain: string; snippet?: string; kind?: string }[]
  webcamItems: UnifiedGalleryItem[]
  currentItems: UnifiedGalleryItem[]

  // Stories (separate from gallery items — uses NewsItemData)
  storiesItems: import('../../../types/news').NewsItemData[]
  isLoadingStories: boolean

  // Loading states (names match GalleryTabs props directly)
  isLoadingImages: boolean
  isLoadingVideos: boolean
  isLoadingMaps: boolean
  isLoadingModels: boolean
  isLoadingArtifacts: boolean
  isLoadingBooks: boolean
  isLoadingPapers: boolean
  isLoadingWebcams: boolean
  isLoadingReferences: boolean
  isLoading: boolean

  // Hero
  heroImage: HeroImage | null
  heroImageSrc: string | undefined
  setHeroImageSrc: ((src: string) => void) | undefined

  // Compat for ModelViewer
  sketchfabModels: SketchfabModelCompat[]

  // Sketchfab category filter toggle
  sketchfabCategoryFilter: boolean
  setSketchfabCategoryFilter: (value: boolean) => void

  // Connector status metadata
  sourcesSearched: string[]
  sourcesFailed: string[]
  itemsBySource: Record<string, number>
  searchTimeMs: number
}
