import type { GalleryImage } from '../ImageGallery'
import type { AncientMap } from '../../services/ancientMapsService'
import type { SketchfabModel } from '../../services/sketchfabService'
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
export type GalleryTab = 'photos' | 'maps' | '3dmodels' | 'artifacts' | 'artworks' | 'texts' | 'myths'

// Unified gallery item type for all tabs
export interface UnifiedGalleryItem {
  id: string
  thumb: string
  full: string
  title?: string
  date?: string
  source: 'wikipedia' | 'map' | 'artifact' | 'sketchfab'
  // Original data for lightbox
  original: GalleryImage | AncientMap | Artifact | SketchfabModel
}

// ============= Popup Data Types (Discriminated Union) =============

/** Empire data for empire popup mode */
export interface EmpirePopupData {
  id: string
  name: string
  region: string
  startYear: number
  endYear: number
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
  prefetchedImages?: { wiki: GalleryImage[] } | null
  onSetProximity?: (coords: [number, number]) => void
  onFlyTo?: (coords: [number, number]) => void
  onHighlight?: (siteId: string | null) => void
  onSelect?: (siteId: string, ctrlKey: boolean) => void
  isStandalone?: boolean
  onMinimizedChange?: (isMinimized: boolean) => void
  minimizedStackIndex?: number
  isLoadingImages?: boolean
  onSiteUpdate?: (siteId: string, updatedSite: SiteData) => void

  // Empire mode props
  empire?: EmpirePopupData
  empireYear?: number
  empireYearOptions?: number[]
  onEmpireYearChange?: (year: number) => void
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

export interface DescriptionSectionProps {
  description?: string
  sourceId: string
  rawData: Record<string, unknown> | null
  rawDataLoading: boolean
  sourceUrl?: string
  onAdminClick: () => void
  isEmpireMode?: boolean
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
  onEmpireYearChange?: (year: number) => void

  // Google Maps state
  googleMapsLoaded: boolean
  googleMapsError: boolean
  showStreetView: boolean
  isMapFullscreen: boolean
  shareSuccess: boolean
  siteShareSuccess: boolean

  // Handlers
  onGoogleMapsLoad: () => void
  onGoogleMapsError: () => void
  onStreetViewToggle: () => void
  onFullscreenToggle: () => void
  onShareGoogleMaps: () => void
  onShareSite: () => void

  // Other
  siteId: string
  isStandalone?: boolean
  mapSectionRef: React.RefObject<HTMLDivElement>
}

// ============= Empire Seshat Tab Types =============

export type EmpireSeshatTab = 'overview' | 'stats' | 'military' | 'society' | 'history'

export interface WindowControlsProps {
  windowState: WindowState
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
  mapCount: number
  modelCount: number
  artifactCount: number
  artworkCount: number
  textCount: number
  mythCount: number
  isLoadingImages?: boolean
  isLoadingMaps?: boolean
  isLoadingModels?: boolean
  isGalleryExpanded: boolean
  onExpandToggle: () => void
}

export interface GalleryGridProps {
  items: UnifiedGalleryItem[]
  onItemClick: (index: number) => void
}

export interface GalleryContentProps {
  activeTab: GalleryTab
  items: UnifiedGalleryItem[]
  isLoading: boolean
  isOffline: boolean
  onItemClick: (index: number) => void
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
