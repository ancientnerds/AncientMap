import type { GalleryImage } from '../ImageGallery'
import type { SiteData } from '../../data/sites'
import type { SeshatPolityData } from '../../types/seshat'

// Artifact type (placeholder - API disabled)
export interface Artifact {
  id: number
  title: string
  thumbnail: string
  fullImage: string
  date?: string
  sourceUrl: string
}

// Gallery tab options
export type GalleryTab = 'photos' | 'videos' | 'maps' | '3dmodels' | 'artifacts' | 'artworks' | 'books' | 'papers' | 'myths'

// Unified gallery item type for all tabs
export interface UnifiedGalleryItem {
  id: string
  thumb: string
  full: string
  title?: string
  date?: string
  // Source can be any connector ID from the backend
  source: 'wikipedia' | 'map' | 'artifact' | 'sketchfab' | 'smithsonian'
        | 'met_museum' | 'europeana' | 'british_museum' | 'loc'
        | 'david_rumsey' | 'wikimedia' | 'wikimedia_commons' | string
  // Original data for lightbox - can be ContentItem or legacy types
  original: GalleryImage | Record<string, unknown>
}

// ============= Popup Data Types (Discriminated Union) =============

/** Empire data for empire popup mode */
export interface EmpirePopupData {
  id: string
  name: string
  region: string
  color: number
  peakYear?: number
  peakArea?: number
  /** Seshat polity data - loaded from bundled data */
  seshatData?: SeshatPolityData
}

/** Site data extends from SiteData in data/sites */
export type SitePopupData = SiteData

/** Discriminated union for popup data */
export type PopupData =
  | { type: 'site'; data: SitePopupData }
  | { type: 'empire'; data: EmpirePopupData }

// Type guards
export function isSitePopup(popup: PopupData): popup is { type: 'site'; data: SitePopupData } {
  return popup.type === 'site'
}

export function isEmpirePopup(popup: PopupData): popup is { type: 'empire'; data: EmpirePopupData } {
  return popup.type === 'empire'
}

// ============= Window State Types =============

export type WindowState = 'normal' | 'minimized' | 'maximized'

export interface WindowPosition {
  x: number
  y: number
}

export interface WindowSize {
  width: number
  height: number
}

export interface WindowDragStart {
  x: number
  y: number
  posX: number
  posY: number
}

export interface WindowResizeStart {
  x: number
  y: number
  width: number
  height: number
  posX: number
  posY: number
}

// ============= Props Types =============

export interface SitePopupProps {
  site?: SiteData
  onClose: () => void
  onSetProximity?: (coords: [number, number]) => void
  onFlyTo?: (coords: [number, number]) => void
  onHighlight?: (siteId: string | null) => void
  onSelect?: (siteId: string, ctrlKey: boolean) => void
  isStandalone?: boolean
  onMinimizedChange?: (isMinimized: boolean) => void
  minimizedStackIndex?: number
  onSiteUpdate?: (siteId: string, updatedSite: SiteData) => void
  onAskLyra?: (contextType: 'site' | 'empire', contextId: string, contextYear?: number) => void

  // Empire mode props
  empire?: EmpirePopupData
  empireYear?: number
  empireYearOptions?: number[]
  empireDefaultYear?: number
  onEmpireYearChange?: (year: number) => void
}

// ============= Alternate Source Types =============

export interface AlternateSource {
  id: string
  sourceId: string
  sourceName: string
  sourceColor: string
  name: string
  sourceUrl?: string
  description?: string
  thumbnailUrl?: string
  siteType?: string
  periodName?: string
  periodStart?: number | null
  country?: string
  lat: number
  lon: number
}

// ============= Component Props =============

export interface HeroHeaderProps {
  title: string
  heroImageSrc?: string
  isLoadingImages?: boolean
  sourceInfo: { name: string; url?: string } | undefined
  sourceName: string
  sourceColor: string
  category: string
  period: string
  catColor: string
  periodColor: string
  titleCopied: boolean
  onTitleCopy: () => void
  onTitleBarMouseDown?: (e: React.MouseEvent) => void
  onTitleBarDoubleClick?: () => void
  isStandalone?: boolean
  windowState?: WindowState
  isEmpireMode?: boolean
  alternateSources?: AlternateSource[]
  activeSiteId?: string
  siteId?: string
  onSourceSelect?: (alt: AlternateSource | null) => void
  onAskLyra?: () => void
  onShareSite?: () => void
  siteShareSuccess?: boolean
}

export interface LocationSectionProps {
  location?: string
  lat: number
  lng: number
  coordsCopied: boolean
  onCoordsCopy: () => void
  onSetProximity?: (coords: [number, number]) => void
  onMinimize?: () => void
}

export interface ReferenceLink {
  url: string
  title: string
  domain: string
  kind: string  // article, academic, database, museum, unesco, government, project
}

export interface DescriptionSectionProps {
  description?: string
  sourceId: string
  rawData: Record<string, unknown> | null
  rawDataLoading: boolean
  sourceUrl?: string
  onAdminClick: () => void
  isEmpireMode?: boolean
  isFounder?: boolean
  bestWikiUrl?: string
  sourceLanguage?: string
  referenceLinks?: ReferenceLink[]
}

export interface MapSectionProps {
  // Site mode props
  lat: number
  lng: number
  location?: string
  isWaterLocation: boolean

  // Empire mode props
  isEmpireMode: boolean
  empire?: EmpirePopupData
  empireYear?: number
  empireYearOptions?: number[]
  empireDefaultYear?: number
  onEmpireYearChange?: (year: number) => void

  // Google Maps state
  googleMapsLoaded: boolean
  googleMapsError: boolean
  showStreetView: boolean
  isMapFullscreen: boolean
  shareSuccess: boolean

  // Handlers
  onGoogleMapsLoad: () => void
  onGoogleMapsError: () => void
  onStreetViewToggle: () => void
  onFullscreenToggle: () => void
  onShareGoogleMaps: () => void

  // Other
  mapSectionRef: React.RefObject<HTMLDivElement>
}

// ============= Empire Seshat Tab Types =============

export type EmpireSeshatTab = 'overview' | 'stats' | 'military' | 'society' | 'history'

export interface WindowControlsProps {
  windowState: WindowState
  siteId?: string
  isEmpireMode?: boolean
  onMinimize: (e: React.MouseEvent) => void
  onMaximize: (e: React.MouseEvent) => void
  onClose: () => void
}

export interface ResizeHandlesProps {
  onStartResize: (e: React.MouseEvent, direction: string) => void
}

export interface MinimizedBarProps {
  title: string
  siteId: string
  coordinates: [number, number]
  isEmpireMode?: boolean
  onRestore: (e: React.MouseEvent) => void
  onClose: (e: React.MouseEvent) => void
  onHighlight?: (siteId: string | null) => void
  onSelect?: (siteId: string, ctrlKey: boolean) => void
  onFlyTo?: (coords: [number, number]) => void
  tooltipPinnedRef: React.MutableRefObject<boolean>
}

export interface GalleryTabsProps {
  activeTab: GalleryTab
  onTabChange: (tab: GalleryTab) => void
  photoCount: number
  videoCount: number
  mapCount: number
  modelCount: number
  artifactCount: number
  artworkCount: number
  bookCount: number
  paperCount: number
  mythCount: number
  isLoadingImages?: boolean
  isLoadingVideos?: boolean
  isLoadingMaps?: boolean
  isLoadingModels?: boolean
  isLoadingArtifacts?: boolean
  isLoadingBooks?: boolean
  isLoadingPapers?: boolean
}

export interface GalleryGridProps {
  items: UnifiedGalleryItem[]
  onItemClick: (index: number) => void
  isExpanded?: boolean
}

export interface GalleryContentProps {
  activeTab: GalleryTab
  items: UnifiedGalleryItem[]
  isLoading: boolean
  isOffline: boolean
  onItemClick: (index: number) => void
  isExpanded?: boolean
}

export interface AdminEditPanelProps {
  site: SiteData
  editedSite: SiteData
  onEditedSiteChange: (site: SiteData) => void
  saveError: string | null
  isSaving: boolean
  onSave: () => void
  onCancel: () => void
}
