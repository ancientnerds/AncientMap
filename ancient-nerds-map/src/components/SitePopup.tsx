import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { SiteData, CATEGORY_COLORS, PERIOD_COLORS, getSourceColor, getCategoryColor, getSourceInfo } from '../data/sites'
import type { GalleryImage } from './ImageGallery'
import { isWikipediaUrl } from '../services/imageService'
import { getCountryFlatFlagUrl } from '../utils/countryFlags'
import { findMapsForLocation, AncientMap } from '../services/ancientMapsService'
import { findModelsForSite, SketchfabModel } from '../services/sketchfabService'
import { getStreetViewEmbedUrl } from '../services/streetViewService'
import { config } from '../config'
import { useOffline } from '../contexts/OfflineContext'
// Artifacts API disabled - will be placeholder for now
// import { findArtifactsForSite, Artifact } from '../services/artifactsService'
type Artifact = { id: number; title: string; thumbnail: string; fullImage: string; date?: string; sourceUrl: string }
import ImageLightbox, { LightboxImage } from './ImageLightbox'
import ModelViewer from './ModelViewer'
import PinAuthModal from './PinAuthModal'
import SiteMetadata from './SiteMetadata'
import { hasMetadataFields } from '../config/sourceFields'

interface SitePopupProps {
  site: SiteData
  onClose: () => void
  prefetchedImages?: { wiki: GalleryImage[] } | null
  onSetProximity?: (coords: [number, number]) => void
  onFlyTo?: (coords: [number, number]) => void  // Fly globe to coordinates
  onHighlight?: (siteId: string | null) => void  // Highlight site on globe (reuses existing system)
  onSelect?: (siteId: string, ctrlKey: boolean) => void  // Select site (supports multi-select with Ctrl)
  isStandalone?: boolean
  onMinimizedChange?: (isMinimized: boolean) => void
  minimizedStackIndex?: number  // -1 = not minimized, 0+ = position in stack
  isLoadingImages?: boolean  // Show shimmer while images are loading
  onSiteUpdate?: (siteId: string, updatedSite: SiteData) => void  // Callback when site is updated via admin edit
}

type GalleryTab = 'photos' | 'maps' | '3dmodels' | 'artifacts' | 'artworks' | 'texts' | 'myths'

// Unified gallery item type for all tabs
interface UnifiedGalleryItem {
  id: string
  thumb: string
  full: string
  title?: string
  date?: string
  source: 'wikipedia' | 'map' | 'artifact' | 'sketchfab'
  // Original data for lightbox
  original: GalleryImage | AncientMap | Artifact | SketchfabModel
}

export default function SitePopup({ site, onClose, prefetchedImages, onSetProximity, onFlyTo, onHighlight, onSelect, isStandalone = false, onMinimizedChange, minimizedStackIndex = -1, isLoadingImages = false, onSiteUpdate }: SitePopupProps) {
  // Offline mode context
  const { isOffline } = useOffline()

  // Local site data that can be updated after save (overrides prop)
  const [localSite, setLocalSite] = useState<SiteData>(site)
  const displaySite = localSite

  const [shareSuccess, setShareSuccess] = useState(false) // Google Maps share
  const [siteShareSuccess, setSiteShareSuccess] = useState(false) // Site popup share
  const [coordsCopied, setCoordsCopied] = useState(false)
  const [titleCopied, setTitleCopied] = useState(false)
  const [googleMapsLoaded, setGoogleMapsLoaded] = useState(false)
  const [googleMapsError, setGoogleMapsError] = useState(false)

  // Street View toggle state
  const [showStreetView, setShowStreetView] = useState(false)
  const [isMapFullscreen, setIsMapFullscreen] = useState(false)
  const mapSectionRef = useRef<HTMLDivElement>(null)

  // Handle fullscreen change events (e.g., user presses Escape)
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsMapFullscreen(!!document.fullscreenElement)
    }
    document.addEventListener('fullscreenchange', handleFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange)
  }, [])

  // Toggle native browser fullscreen
  const toggleMapFullscreen = useCallback(async () => {
    if (!mapSectionRef.current) return

    if (!document.fullscreenElement) {
      try {
        await mapSectionRef.current.requestFullscreen()
        setIsMapFullscreen(true)
      } catch (err) {
        console.warn('Fullscreen request failed:', err)
      }
    } else {
      await document.exitFullscreen()
      setIsMapFullscreen(false)
    }
  }, [])

  // Detect underwater/water locations where satellite imagery is unavailable
  const isWaterLocation = useMemo(() => {
    const waterKeywords = ['sea', 'ocean', 'lake', 'underwater', 'submerged', 'sunken']
    const locationLower = (displaySite.location || '').toLowerCase()
    const titleLower = displaySite.title.toLowerCase()
    return waterKeywords.some(kw => locationLower.includes(kw) || titleLower.includes(kw))
  }, [displaySite.location, displaySite.title])
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

  // Model viewer state (for 3D models fullscreen)
  const [modelViewerIndex, setModelViewerIndex] = useState<number | null>(null)

  // Lightbox state
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)
  const [lightboxItems, setLightboxItems] = useState<LightboxImage[]>([])

  // Admin mode state
  const [showAdminPin, setShowAdminPin] = useState(false)
  const [isAdminMode, setIsAdminMode] = useState(false)
  const [editedSite, setEditedSite] = useState<SiteData | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Raw metadata for source-specific fields (earthquakes, volcanoes, etc.)
  const [rawData, setRawData] = useState<Record<string, unknown> | null>(null)
  const [rawDataLoading, setRawDataLoading] = useState(false)

  // Window management state
  const [windowState, setWindowState] = useState<'normal' | 'minimized' | 'maximized'>('normal')
  const [position, setPosition] = useState({ x: 0, y: 0 })
  const [size, setSize] = useState({ width: 0, height: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const [isResizing, setIsResizing] = useState(false)
  const [resizeDirection, setResizeDirection] = useState('')
  const [isPositioned, setIsPositioned] = useState(false)

  // Refs for window management
  const popupRef = useRef<HTMLDivElement>(null)
  const dragStartRef = useRef({ x: 0, y: 0, posX: 0, posY: 0 })
  const resizeStartRef = useRef({ x: 0, y: 0, width: 0, height: 0, posX: 0, posY: 0 })

  // Saved state for restore from maximize
  const savedStateRef = useRef({ x: 0, y: 0, width: 0, height: 0 })

  // Track if tooltip was pinned by clicking minimized bar (prevents mouse leave from clearing)
  const tooltipPinnedRef = useRef(false)

  const catColor = getCategoryColor(displaySite.category)
  const periodColor = PERIOD_COLORS[displaySite.period] || '#888'
  const sourceColor = getSourceColor(displaySite.sourceId)
  const sourceInfo = getSourceInfo(displaySite.sourceId)
  // Always use sourceInfo for display name - single source of truth
  const sourceName = sourceInfo?.name || displaySite.sourceId

  const [lng, lat] = displaySite.coordinates

  // Sync internal windowState with parent's minimized state (via minimizedStackIndex prop)
  // This allows the parent to restore a minimized popup by setting isMinimized=false
  useEffect(() => {
    if (minimizedStackIndex >= 0 && windowState !== 'minimized') {
      // Parent says we should be minimized but we're not
      setWindowState('minimized')
    } else if (minimizedStackIndex === -1 && windowState === 'minimized') {
      // Parent says we should NOT be minimized but we are - restore to normal
      setWindowState('normal')
    }
  }, [minimizedStackIndex, windowState])

  // Track if we've already fetched for this site (prevents re-fetching loops)
  const mapsFetchedRef = useRef<string | null>(null)
  const sketchfabFetchedRef = useRef<string | null>(null)

  // Load priority: hero image -> popup opens -> google map -> wiki -> 3D -> maps
  // Maps load after a delay to prioritize images and 3D
  useEffect(() => {
    const siteKey = `${displaySite.title}-${lat}-${lng}`

    // Skip if already fetched for this site
    if (mapsFetchedRef.current === siteKey) return

    setAncientMapsLoading(true)
    const timer = setTimeout(() => {
      mapsFetchedRef.current = siteKey
      findMapsForLocation(lat, lng, displaySite.title, displaySite.location || '')
        .then(setAncientMaps)
        .catch((err) => {
          console.warn('Failed to load ancient maps:', err)
          setAncientMaps([])
        })
        .finally(() => setAncientMapsLoading(false))
    }, 1500) // 1.5s delay after popup opens (after 3D models)

    return () => clearTimeout(timer)
  }, [lat, lng, displaySite.title, displaySite.location])

  // Sketchfab 3D models load after photos (1s delay)
  useEffect(() => {
    const siteKey = displaySite.title

    // Skip if already fetched for this site or offline
    if (sketchfabFetchedRef.current === siteKey || isOffline) return

    setSketchfabLoading(true)
    const timer = setTimeout(() => {
      sketchfabFetchedRef.current = siteKey
      findModelsForSite(displaySite.title)
        .then(setSketchfabModels)
        .catch((err) => {
          console.warn('Failed to load 3D models:', err)
          setSketchfabModels([])
        })
        .finally(() => setSketchfabLoading(false))
    }, 1000) // 1s delay after popup opens

    return () => clearTimeout(timer)
  }, [displaySite.title, isOffline])

  // Reset Street View when coordinates change
  useEffect(() => {
    setShowStreetView(false)
  }, [lat, lng])

  // Fetch rawData for sources with metadata fields (earthquakes, volcanoes, etc.)
  useEffect(() => {
    // Only fetch if the source has displayable metadata fields
    if (!hasMetadataFields(displaySite.sourceId)) {
      setRawData(null)
      return
    }

    // Fetch site details to get rawData
    setRawDataLoading(true)
    fetch(`${config.api.baseUrl}/sites/${site.id}`)
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data?.rawData) {
          setRawData(data.rawData)
        }
      })
      .catch(err => {
        console.warn('Failed to fetch site rawData:', err)
      })
      .finally(() => setRawDataLoading(false))
  }, [site.id, displaySite.sourceId])

  // DISABLED: Artifacts section is placeholder only
  //   // Artifacts load after maps
  //   useEffect(() => {
  //     const timer = setTimeout(() => {
  //       if (!artifactsLoading && artifacts.length === 0) {
  //         setArtifactsLoading(true)
  //         findArtifactsForSite(site.title, site.location || '')
  //           .then(setArtifacts)
  //           .catch((err) => {
  //             console.warn('Failed to load artifacts:', err)
  //             setArtifacts([])
  //           })
  //           .finally(() => setArtifactsLoading(false))
  //       }
  //     }, 2000) // 2s delay
  //     return () => clearTimeout(timer)
  //   }, [site.title, site.location, artifactsLoading, artifacts.length])

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

  const formatCoord = (coord: number, isLat: boolean) => {
    const abs = Math.abs(coord)
    const dir = isLat ? (coord >= 0 ? 'N' : 'S') : (coord >= 0 ? 'E' : 'W')
    return `${abs.toFixed(4)}° ${dir}`
  }

  // Google Maps URLs - zoomed out 3 steps (18 -> 15)
  const googleMapsUrl = `https://www.google.com/maps/@${lat},${lng},15z/data=!3m1!1e3`
  const googleMapsEmbedUrl = `https://www.google.com/maps/embed?pb=!1m14!1m12!1m3!1d4000!2d${lng}!3d${lat}!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!5e1!3m2!1sen!2sus!4v1234567890`
  const streetViewEmbedUrl = getStreetViewEmbedUrl(lat, lng)

  // URL to open standalone popup in new tab (direct SPA link)
  const sitePopupUrl = `${window.location.origin}${window.location.pathname}?site=${site.id}`

  // Share URL with OG meta tags for social media previews
  // Uses the API share endpoint which has proper og:image, og:title etc.
  const shareUrl = `${config.api.baseUrl}/og/share/${site.id}`

  // Share site popup URL (with OG tags for social media previews)
  const handleShareSite = async () => {
    try {
      if (navigator.share) {
        await navigator.share({
          title: displaySite.title,
          text: `${displaySite.title} - Archaeological Site`,
          url: shareUrl
        })
      } else {
        await navigator.clipboard.writeText(`${displaySite.title}\n${shareUrl}`)
        setSiteShareSuccess(true)
        setTimeout(() => setSiteShareSuccess(false), 2000)
      }
    } catch {
      console.log('Share cancelled')
    }
  }

  // Share Google Maps location
  const handleShareGoogleMaps = async () => {
    try {
      if (navigator.share) {
        await navigator.share({
          title: displaySite.title,
          text: `${displaySite.title} - Archaeological Site`,
          url: googleMapsUrl
        })
      } else {
        await navigator.clipboard.writeText(`${displaySite.title}\n${googleMapsUrl}`)
        setShareSuccess(true)
        setTimeout(() => setShareSuccess(false), 2000)
      }
    } catch {
      console.log('Share cancelled')
    }
  }

  // ============= WINDOW MANAGEMENT =============
  const MIN_WIDTH = 400
  const MIN_HEIGHT = 300

  // Initialize position and size on mount
  useEffect(() => {
    if (popupRef.current && !isPositioned && !isStandalone) {
      const rect = popupRef.current.getBoundingClientRect()
      const initialWidth = rect.width
      const initialHeight = rect.height
      setSize({ width: initialWidth, height: initialHeight })
      setPosition({
        x: (window.innerWidth - initialWidth) / 2,
        y: (window.innerHeight - initialHeight) / 2
      })
      savedStateRef.current = {
        x: (window.innerWidth - initialWidth) / 2,
        y: (window.innerHeight - initialHeight) / 2,
        width: initialWidth,
        height: initialHeight
      }
      setIsPositioned(true)
    }
  }, [isPositioned, isStandalone])

  // Title bar drag handlers
  const handleTitleBarMouseDown = useCallback((e: React.MouseEvent) => {
    if (windowState === 'maximized' || isStandalone) return
    e.preventDefault()
    setIsDragging(true)
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      posX: position.x,
      posY: position.y
    }
  }, [windowState, position, isStandalone])

  // Double-click to toggle maximize
  const handleTitleBarDoubleClick = useCallback(() => {
    if (isStandalone) return
    if (windowState === 'maximized') {
      setWindowState('normal')
      setPosition({ x: savedStateRef.current.x, y: savedStateRef.current.y })
      setSize({ width: savedStateRef.current.width, height: savedStateRef.current.height })
    } else {
      savedStateRef.current = { x: position.x, y: position.y, width: size.width, height: size.height }
      setWindowState('maximized')
    }
  }, [windowState, position, size, isStandalone])

  // Resize handlers
  const startResize = useCallback((e: React.MouseEvent, direction: string) => {
    if (windowState !== 'normal' || isStandalone) return
    e.preventDefault()
    e.stopPropagation()
    setIsResizing(true)
    setResizeDirection(direction)
    resizeStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      width: size.width,
      height: size.height,
      posX: position.x,
      posY: position.y
    }
  }, [windowState, size, position, isStandalone])

  // Window control actions
  const handleMinimize = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    if (windowState === 'minimized') {
      // Restoring from minimized - clamp position to fit on screen
      const newX = Math.max(0, Math.min(window.innerWidth - size.width, position.x))
      const newY = Math.max(0, Math.min(window.innerHeight - size.height, position.y))
      setPosition({ x: newX, y: newY })
      setWindowState('normal')
      onMinimizedChange?.(false)
    } else {
      setWindowState('minimized')
      onMinimizedChange?.(true)
    }
  }, [windowState, position, size, onMinimizedChange])

  const handleMaximize = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    if (windowState === 'maximized') {
      // Restoring from maximized - clamp position to fit on screen
      const restoreWidth = savedStateRef.current.width
      const restoreHeight = savedStateRef.current.height
      const newX = Math.max(0, Math.min(window.innerWidth - restoreWidth, savedStateRef.current.x))
      const newY = Math.max(0, Math.min(window.innerHeight - restoreHeight, savedStateRef.current.y))
      setPosition({ x: newX, y: newY })
      setSize({ width: restoreWidth, height: restoreHeight })
      setWindowState('normal')
    } else {
      // Save current state before maximizing (only if not minimized)
      if (windowState !== 'minimized') {
        savedStateRef.current = { x: position.x, y: position.y, width: size.width, height: size.height }
      }
      setWindowState('maximized')
    }
  }, [windowState, position, size])

  // Global mouse move/up handlers for drag and resize
  useEffect(() => {
    if (isStandalone) return

    const handleMouseMove = (e: MouseEvent) => {
      if (isDragging) {
        const deltaX = e.clientX - dragStartRef.current.x
        const deltaY = e.clientY - dragStartRef.current.y
        let newX = dragStartRef.current.posX + deltaX
        let newY = dragStartRef.current.posY + deltaY

        // Use actual current dimensions (minimized = 280x32, otherwise stored size)
        const currentWidth = windowState === 'minimized' ? 280 : size.width
        const currentHeight = windowState === 'minimized' ? 32 : size.height

        // Keep within bounds
        newX = Math.max(0, Math.min(window.innerWidth - currentWidth, newX))
        newY = Math.max(0, Math.min(window.innerHeight - currentHeight, newY))

        setPosition({ x: newX, y: newY })
      }

      if (isResizing) {
        const deltaX = e.clientX - resizeStartRef.current.x
        const deltaY = e.clientY - resizeStartRef.current.y
        let newWidth = resizeStartRef.current.width
        let newHeight = resizeStartRef.current.height
        let newX = resizeStartRef.current.posX
        let newY = resizeStartRef.current.posY

        // Handle resize based on direction
        if (resizeDirection.includes('e')) {
          newWidth = Math.max(MIN_WIDTH, resizeStartRef.current.width + deltaX)
        }
        if (resizeDirection.includes('w')) {
          const widthChange = Math.min(deltaX, resizeStartRef.current.width - MIN_WIDTH)
          newWidth = resizeStartRef.current.width - widthChange
          newX = resizeStartRef.current.posX + widthChange
        }
        if (resizeDirection.includes('s')) {
          newHeight = Math.max(MIN_HEIGHT, resizeStartRef.current.height + deltaY)
        }
        if (resizeDirection.includes('n')) {
          const heightChange = Math.min(deltaY, resizeStartRef.current.height - MIN_HEIGHT)
          newHeight = resizeStartRef.current.height - heightChange
          newY = resizeStartRef.current.posY + heightChange
        }

        // Clamp to screen bounds
        newWidth = Math.min(newWidth, window.innerWidth - newX)
        newHeight = Math.min(newHeight, window.innerHeight - newY)
        newX = Math.max(0, newX)
        newY = Math.max(0, newY)

        setSize({ width: newWidth, height: newHeight })
        setPosition({ x: newX, y: newY })
      }
    }

    const handleMouseUp = () => {
      setIsDragging(false)
      setIsResizing(false)
      setResizeDirection('')
    }

    if (isDragging || isResizing) {
      window.addEventListener('mousemove', handleMouseMove)
      window.addEventListener('mouseup', handleMouseUp)
      return () => {
        window.removeEventListener('mousemove', handleMouseMove)
        window.removeEventListener('mouseup', handleMouseUp)
      }
    }
  }, [isDragging, isResizing, resizeDirection, size.width, size.height, isStandalone, windowState])

  // Compute popup style based on window state
  const popupStyle = useMemo(() => {
    if (isStandalone) return {}
    if (!isPositioned) return { opacity: 0, zIndex: 1000 } // Hide until positioned

    if (windowState === 'maximized') {
      return {
        position: 'fixed' as const,
        top: 0,
        left: 0,
        width: '100vw',
        height: '100vh',
        borderRadius: 0,
        zIndex: 1000
      }
    }

    // Minimized: stack at lower-left corner
    if (windowState === 'minimized') {
      const stackOffset = (minimizedStackIndex >= 0 ? minimizedStackIndex : 0) * 40 // 32px height + 8px gap
      return {
        position: 'fixed' as const,
        left: 20,
        bottom: 20 + stackOffset,
        width: 280, // Compact width for minimized state
        height: 32,
        zIndex: 1000 + (minimizedStackIndex >= 0 ? minimizedStackIndex : 0)
      }
    }

    return {
      position: 'fixed' as const,
      left: position.x,
      top: position.y,
      width: size.width || undefined,
      height: size.height || undefined,
      zIndex: 1000
    }
  }, [isStandalone, isPositioned, windowState, position, size, minimizedStackIndex])

  // Handle gallery item click - open lightbox or model viewer
  const handleItemClick = (index: number) => {
    const items = currentItems

    // For 3D models, open the ModelViewer instead of lightbox
    if (activeGalleryTab === '3dmodels') {
      setModelViewerIndex(index)
      return
    }

    const lightboxImages: LightboxImage[] = items.map(item => {
      const orig = item.original
      if (item.source === 'wikipedia') {
        const img = orig as GalleryImage
        return {
          src: img.full,
          title: img.title,
          photographer: img.photographer,
          photographerUrl: img.photographerUrl,
          sourceType: 'wikimedia',
          sourceUrl: img.wikimediaUrl,
          license: img.license
        }
      } else if (item.source === 'map') {
        const map = orig as AncientMap
        return {
          src: map.fullImage,
          title: map.title,
          photographer: map.date || undefined,
          sourceType: 'david-rumsey',
          sourceUrl: map.webUrl
        }
      } else {
        const artifact = orig as Artifact
        return {
          src: artifact.fullImage,
          title: artifact.title,
          photographer: artifact.date || undefined,
          sourceType: 'met-museum',
          sourceUrl: artifact.sourceUrl
        }
      }
    })
    setLightboxItems(lightboxImages)
    setLightboxIndex(index)
  }

  // Render unified gallery grid
  const renderGalleryContent = () => {
    // Maps tab - show offline notice when offline
    if (activeGalleryTab === 'maps' && isOffline) {
      return (
        <div className="gallery-grid-container">
          <div className="gallery-empty gallery-offline-notice">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.5">
              <path d="M12 22s-8-4.5-8-11.8A8 8 0 0 1 12 2a8 8 0 0 1 8 8.2c0 7.3-8 11.8-8 11.8z"/>
              <circle cx="12" cy="10" r="3"/>
              <line x1="2" y1="2" x2="22" y2="22" strokeWidth="2"/>
            </svg>
            <span>Historical maps require internet</span>
            <span className="gallery-subtext">David Rumsey Map Collection is online-only</span>
          </div>
        </div>
      )
    }

    // 3D Models tab - show offline notice when offline
    if (activeGalleryTab === '3dmodels' && isOffline) {
      return (
        <div className="gallery-grid-container">
          <div className="gallery-empty gallery-offline-notice">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.5">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
              <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
              <line x1="12" y1="22.08" x2="12" y2="12"/>
              <line x1="2" y1="2" x2="22" y2="22" strokeWidth="2"/>
            </svg>
            <span>3D models require internet</span>
            <span className="gallery-subtext">Sketchfab viewer is online-only</span>
          </div>
        </div>
      )
    }

    // Artifacts tab is placeholder only - show Coming Soon
    if (activeGalleryTab === 'artifacts') {
      return (
        <div className="gallery-grid-container">
          <div className="gallery-empty">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.5">
              <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
              <path d="M2 17l10 5 10-5"></path>
              <path d="M2 12l10 5 10-5"></path>
            </svg>
            <span>Coming Soon</span>
          </div>
        </div>
      )
    }

    if (isLoading) {
      return (
        <div className="gallery-grid-container">
          <div className="gallery-loading">
            <div className="map-loading-spinner" />
          </div>
        </div>
      )
    }

    if (currentItems.length === 0) {
      return (
        <div className="gallery-grid-container">
          <div className="gallery-empty">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.5">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <polyline points="21 15 16 10 5 21" />
            </svg>
            <span>No {activeGalleryTab} found</span>
          </div>
        </div>
      )
    }

    return (
      <div className="gallery-grid-container">
        <div className="gallery-grid">
          {currentItems.map((item, index) => (
            <div
              key={item.id}
              className="gallery-item"
              onClick={() => handleItemClick(index)}
              title={item.title || 'Click to enlarge'}
            >
              <img
                src={item.thumb}
                alt={item.title || ''}
                loading="lazy"
                onError={(e) => {
                  e.currentTarget.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect fill="%23333" width="100" height="100"/></svg>'
                }}
              />
              {item.source === 'wikipedia' && (
                <div className="gallery-item-badge wikipedia">W</div>
              )}
              {item.source === 'sketchfab' && (
                <div className="gallery-item-badge sketchfab" title="3D Model">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                  </svg>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    )
  }

  // Admin mode save handler
  const handleSave = async () => {
    if (!editedSite) return
    setIsSaving(true)
    setSaveError(null)
    try {
      const response = await fetch(`${config.api.baseUrl}/sites/${site.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editedSite)
      })
      if (response.ok) {
        // Clear Service Worker cache for sites API to ensure fresh data on refresh
        if ('caches' in window) {
          try {
            const cache = await caches.open('api-sites')
            const keys = await cache.keys()
            await Promise.all(keys.map(key => cache.delete(key)))
            console.log('[Admin] Cleared Service Worker sites cache')
          } catch (e) {
            console.warn('[Admin] Could not clear SW cache:', e)
          }
        }
        // Update local state with edited data and exit admin mode
        setLocalSite(editedSite)
        // Notify parent to update sites array for tooltip/UI refresh
        onSiteUpdate?.(site.id, editedSite)
        setIsAdminMode(false)
        setEditedSite(null)
      } else {
        const err = await response.json()
        setSaveError(err.message || 'Failed to save')
      }
    } catch (err) {
      console.error('Failed to save:', err)
      setSaveError('Network error - failed to save')
    }
    setIsSaving(false)
  }

  // Cancel admin edit
  const handleCancelEdit = () => {
    setIsAdminMode(false)
    setEditedSite(null)
    setSaveError(null)
  }

  // Window state class names
  const windowClasses = [
    'site-popup',
    'site-popup-large',
    isStandalone ? 'standalone' : 'windowed',
    windowState === 'minimized' ? 'minimized' : '',
    windowState === 'maximized' ? 'maximized' : '',
    isDragging ? 'dragging' : '',
    isResizing ? 'resizing' : ''
  ].filter(Boolean).join(' ')

  // In standalone mode, render without overlay wrapper
  const popupContent = (
    <div
      ref={popupRef}
      className={windowClasses}
      style={popupStyle}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Minimized bar - click to select and fly, hover to highlight on globe */}
      {!isStandalone && windowState === 'minimized' && (
        <div
          className="popup-minimized-bar"
          onMouseEnter={() => {
            tooltipPinnedRef.current = false // Reset pin on re-enter for hover behavior
            onHighlight?.(site.id)
          }}
          onMouseLeave={() => {
            // Only clear highlight if not pinned by click
            if (!tooltipPinnedRef.current) {
              onHighlight?.(null)
            }
          }}
          onClick={(e) => {
            tooltipPinnedRef.current = true // Pin the tooltip
            onSelect?.(site.id, e.ctrlKey || e.metaKey) // Select with multi-select support
            onFlyTo?.(site.coordinates)
          }}
        >
          <svg className="popup-minimized-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="10" r="3"/>
            <path d="M12 21.7C17.3 17 20 13 20 10a8 8 0 1 0-16 0c0 3 2.7 7 8 11.7z"/>
          </svg>
          <span className="popup-minimized-title">{displaySite.title}</span>
          <button
            className="popup-minimized-btn"
            onClick={handleMinimize}
            title="Restore"
          >
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5">
              <rect x="1" y="1" width="8" height="8" rx="1" />
            </svg>
          </button>
          <button
            className="popup-minimized-btn close-btn"
            onClick={(e) => { e.stopPropagation(); onClose(); }}
            title="Close"
          >
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5">
              <line x1="2" y1="2" x2="8" y2="8" />
              <line x1="8" y1="2" x2="2" y2="8" />
            </svg>
          </button>
        </div>
      )}

      {/* Window controls - fixed at top right corner (not shown when minimized) */}
      {!isStandalone && windowState !== 'minimized' && (
        <div className="popup-window-controls">
          <button
            className="popup-window-btn"
            onClick={handleMinimize}
            title="Minimize"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
              <line x1="2" y1="6" x2="10" y2="6" />
            </svg>
          </button>
          <button
            className="popup-window-btn"
            onClick={handleMaximize}
            title={windowState === 'maximized' ? 'Restore' : 'Maximize'}
          >
            {windowState === 'maximized' ? (
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="3" y="1" width="7" height="7" rx="1" />
                <path d="M1 3v6a1 1 0 001 1h6" />
              </svg>
            ) : (
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="2" y="2" width="8" height="8" rx="1" />
              </svg>
            )}
          </button>
          <button
            className="popup-window-btn close-btn"
            onClick={onClose}
            title="Close"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
              <line x1="2" y1="2" x2="10" y2="10" />
              <line x1="10" y1="2" x2="2" y2="10" />
            </svg>
          </button>
        </div>
      )}

      {/* Standalone mode close button - returns to globe */}
      {isStandalone && (
        <div className="popup-standalone-close">
          <button
            className="popup-window-btn close-btn"
            onClick={() => {
              window.location.href = 'https://ancientnerds.com'
            }}
            title="Close and return to globe"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
              <line x1="2" y1="2" x2="10" y2="10" />
              <line x1="10" y1="2" x2="2" y2="10" />
            </svg>
          </button>
        </div>
      )}

      {/* Resize handles (only in normal windowed state) */}
      {!isStandalone && windowState === 'normal' && (
        <>
          <div className="resize-handle resize-n" onMouseDown={(e) => startResize(e, 'n')} />
          <div className="resize-handle resize-s" onMouseDown={(e) => startResize(e, 's')} />
          <div className="resize-handle resize-e" onMouseDown={(e) => startResize(e, 'e')} />
          <div className="resize-handle resize-w" onMouseDown={(e) => startResize(e, 'w')} />
          <div className="resize-handle resize-ne" onMouseDown={(e) => startResize(e, 'ne')} />
          <div className="resize-handle resize-nw" onMouseDown={(e) => startResize(e, 'nw')} />
          <div className="resize-handle resize-se" onMouseDown={(e) => startResize(e, 'se')} />
          <div className="resize-handle resize-sw" onMouseDown={(e) => startResize(e, 'sw')} />
        </>
      )}

        <div className="popup-main-layout">
          {/* Left side - Content */}
          <div className="popup-content-side">
            <div
              className="popup-hero-header"
              onMouseDown={!isStandalone ? handleTitleBarMouseDown : undefined}
              onDoubleClick={!isStandalone ? handleTitleBarDoubleClick : undefined}
              style={{ cursor: !isStandalone && windowState !== 'maximized' ? 'move' : undefined }}
            >
              {heroImageSrc ? (
                <img
                  src={heroImageSrc}
                  alt={displaySite.title}
                  className="popup-hero-bg"
                  draggable={false}
                  onError={(e) => { e.currentTarget.style.display = 'none' }}
                />
              ) : isLoadingImages ? (
                <div className="popup-hero-loading">
                  <div className="popup-hero-shimmer" />
                </div>
              ) : null}
              <div className="popup-hero-vignette" />
              <div className="popup-hero-content">
                <div className="popup-title-row">
                  <h2
                    className="popup-title-overlay"
                    style={{
                      fontSize: displaySite.title.length > 50 ? '14px' : displaySite.title.length > 40 ? '16px' : displaySite.title.length > 30 ? '18px' : '22px'
                    }}
                  >{displaySite.title}</h2>
                  <button
                    className={`title-action-btn ${titleCopied ? 'copied' : ''}`}
                    onMouseDown={(e) => e.stopPropagation()}
                    onClick={(e) => {
                      e.stopPropagation()
                      navigator.clipboard.writeText(displaySite.title)
                      setTitleCopied(true)
                      setTimeout(() => setTitleCopied(false), 2000)
                    }}
                    title="Copy name"
                  >
                    {titleCopied ? (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="20 6 9 17 4 12"></polyline>
                      </svg>
                    ) : (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                      </svg>
                    )}
                  </button>
                </div>

                {sourceInfo?.url ? (
                  <a
                    href={sourceInfo.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="popup-source clickable"
                    style={{ borderColor: sourceColor, color: sourceColor }}
                    title={`Visit ${sourceInfo.name}`}
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
                    </svg>
                    {sourceInfo.name}
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="external-icon">
                      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                      <polyline points="15 3 21 3 21 9"></polyline>
                      <line x1="10" y1="14" x2="21" y2="3"></line>
                    </svg>
                  </a>
                ) : (
                  <div className="popup-source" style={{ borderColor: sourceColor, color: sourceColor }}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
                    </svg>
                    {sourceName}
                  </div>
                )}

                <div className="popup-badges">
                  <span className="popup-badge" style={{ borderColor: catColor, color: catColor }}>
                    {displaySite.category}
                  </span>
                  <span className="popup-badge" style={{ borderColor: periodColor, color: periodColor }}>
                    {displaySite.period}
                  </span>
                </div>
              </div>
            </div>

            <div className="popup-body">
              {displaySite.location && (
                <div className="popup-location">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                    <circle cx="12" cy="10" r="3"></circle>
                  </svg>
                  {displaySite.location}
                  {getCountryFlatFlagUrl(displaySite.location) && (
                    <img
                      src={getCountryFlatFlagUrl(displaySite.location)!}
                      alt=""
                      className="country-flag"
                    />
                  )}
                </div>
              )}

              <div className="popup-coordinates">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10"></circle>
                  <line x1="2" y1="12" x2="22" y2="12"></line>
                  <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
                </svg>
                <span className="coords-text">{formatCoord(lat, true)}, {formatCoord(lng, false)}</span>
                <div className="coords-actions">
                  <button
                    className={`coords-action-btn ${coordsCopied ? 'copied' : ''}`}
                    onClick={() => {
                      navigator.clipboard.writeText(`${formatCoord(lat, true)}, ${formatCoord(lng, false)}`)
                      setCoordsCopied(true)
                      setTimeout(() => setCoordsCopied(false), 2000)
                    }}
                    title="Copy coordinates"
                  >
                    {coordsCopied ? (
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="20 6 9 17 4 12"></polyline>
                      </svg>
                    ) : (
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                      </svg>
                    )}
                  </button>
                  {onSetProximity && (
                    <button
                      className="coords-action-btn"
                      onClick={() => {
                        onSetProximity([lng, lat])
                        setWindowState('minimized')
                        onMinimizedChange?.(true)
                      }}
                      title="Search nearby sites"
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <circle cx="12" cy="12" r="3"></circle>
                      </svg>
                    </button>
                  )}
                </div>
              </div>

              {/* Admin Edit Mode */}
              {isAdminMode && editedSite ? (
                <div className="popup-admin-edit">
                  <div className="admin-edit-field">
                    <label>Name</label>
                    <input
                      type="text"
                      value={editedSite.title}
                      onChange={(e) => setEditedSite({ ...editedSite, title: e.target.value })}
                    />
                  </div>
                  <div className="admin-edit-field">
                    <label>Description</label>
                    <textarea
                      value={editedSite.description || ''}
                      onChange={(e) => setEditedSite({ ...editedSite, description: e.target.value })}
                      rows={4}
                    />
                  </div>
                  <div className="admin-edit-field">
                    <label>Location</label>
                    <input
                      type="text"
                      value={editedSite.location || ''}
                      onChange={(e) => setEditedSite({ ...editedSite, location: e.target.value })}
                    />
                  </div>
                  <div className="admin-edit-row">
                    <div className="admin-edit-field">
                      <label>Latitude</label>
                      <input
                        type="number"
                        step="0.0001"
                        value={editedSite.coordinates[1]}
                        onChange={(e) => setEditedSite({
                          ...editedSite,
                          coordinates: [editedSite.coordinates[0], parseFloat(e.target.value) || 0]
                        })}
                      />
                    </div>
                    <div className="admin-edit-field">
                      <label>Longitude</label>
                      <input
                        type="number"
                        step="0.0001"
                        value={editedSite.coordinates[0]}
                        onChange={(e) => setEditedSite({
                          ...editedSite,
                          coordinates: [parseFloat(e.target.value) || 0, editedSite.coordinates[1]]
                        })}
                      />
                    </div>
                  </div>
                  <div className="admin-edit-row">
                    <div className="admin-edit-field">
                      <label>Category</label>
                      <select
                        value={editedSite.category}
                        onChange={(e) => setEditedSite({ ...editedSite, category: e.target.value as SiteData['category'] })}
                      >
                        {Object.keys(CATEGORY_COLORS).map(cat => (
                          <option key={cat} value={cat}>{cat}</option>
                        ))}
                      </select>
                    </div>
                    <div className="admin-edit-field">
                      <label>Period</label>
                      <select
                        value={editedSite.period}
                        onChange={(e) => setEditedSite({ ...editedSite, period: e.target.value as SiteData['period'] })}
                      >
                        {Object.keys(PERIOD_COLORS).map(period => (
                          <option key={period} value={period}>{period}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div className="admin-edit-field">
                    <label>Source URL</label>
                    <input
                      type="url"
                      value={editedSite.sourceUrl || ''}
                      onChange={(e) => setEditedSite({ ...editedSite, sourceUrl: e.target.value })}
                      placeholder="https://..."
                    />
                  </div>
                  {saveError && <div className="admin-edit-error">{saveError}</div>}
                  <div className="admin-edit-actions">
                    <button className="admin-btn cancel" onClick={handleCancelEdit} disabled={isSaving}>
                      Cancel
                    </button>
                    <button className="admin-btn save" onClick={handleSave} disabled={isSaving}>
                      {isSaving ? 'Saving...' : 'Save Changes'}
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  {displaySite.description && (
                    <p className="popup-description">{displaySite.description}</p>
                  )}

                  {/* Source-specific metadata (earthquakes, volcanoes, etc.) */}
                  {!rawDataLoading && (
                    <SiteMetadata sourceId={displaySite.sourceId} rawData={rawData} />
                  )}

                  <div className="popup-links-section">
                    {displaySite.sourceUrl && isWikipediaUrl(displaySite.sourceUrl) && (
                      <a
                        href={displaySite.sourceUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="popup-link-item wikipedia"
                        title="View on Wikipedia"
                      >
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M12.09 13.119c-.936 1.932-2.217 4.548-2.853 5.728-.616 1.074-1.127.931-1.532.029-1.406-3.321-4.293-9.144-5.651-12.409-.251-.601-.441-.987-.619-1.139-.181-.15-.554-.24-1.122-.271C.103 5.033 0 4.982 0 4.898v-.455l.052-.045c.924-.005 5.401 0 5.401 0l.051.045v.434c0 .119-.075.176-.225.176l-.564.031c-.485.029-.727.164-.727.436 0 .135.053.33.166.601 1.082 2.646 4.818 10.521 4.818 10.521l.136.046 2.411-4.81-.482-1.067-1.658-3.264s-.318-.654-.428-.872c-.728-1.443-.712-1.518-1.447-1.617-.207-.023-.313-.05-.313-.149v-.468l.06-.045h4.292l.113.037v.451c0 .105-.076.15-.227.15l-.308.047c-.792.061-.661.381-.136 1.422l1.582 3.252 1.758-3.504c.293-.64.233-.801.111-.947-.07-.084-.305-.22-.812-.24l-.201-.021c-.052 0-.098-.015-.145-.051-.045-.031-.067-.076-.067-.129v-.427l.061-.045c1.247-.008 4.043 0 4.043 0l.059.045v.436c0 .121-.059.178-.193.178-.646.03-.782.095-1.023.439-.12.186-.375.589-.646 1.039l-2.301 4.273-.065.135 2.792 5.712.17.048 4.396-10.438c.154-.422.129-.722-.064-.895-.197-.172-.346-.273-.857-.295l-.42-.016c-.061 0-.105-.014-.152-.045-.043-.029-.072-.075-.072-.119v-.436l.059-.045h4.961l.041.045v.437c0 .119-.074.18-.209.18-.648.03-1.127.18-1.443.421-.314.255-.557.616-.736 1.067 0 0-4.043 9.258-5.426 12.339-.525 1.007-1.053.917-1.503-.031-.571-1.171-1.773-3.786-2.646-5.71l.053-.036z"/>
                        </svg>
                      </a>
                    )}
                    <div className="popup-links-spacer" />
                    {/* Admin button - subtle, on the right */}
                    <button
                      className="popup-link-item admin"
                      onClick={() => setShowAdminPin(true)}
                      title="Admin Edit"
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="3"/>
                        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
                      </svg>
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Right side - Satellite Map */}
          <div className="popup-maps-side">
            <div ref={mapSectionRef} className={`map-section google-map-section active ${isMapFullscreen ? 'fullscreen' : ''}`}>
              {!googleMapsLoaded && !googleMapsError && !isWaterLocation && (
                <div className="map-loading">
                  <div className="map-loading-spinner" />
                </div>
              )}
              {(googleMapsError || isWaterLocation) ? (
                <div className="map-no-data">
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.4">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="2" y1="12" x2="22" y2="12"></line>
                    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
                  </svg>
                  <span>No satellite data</span>
                </div>
              ) : (
                <div className="google-map-container">
                  {showStreetView ? (
                    <iframe
                      src={streetViewEmbedUrl}
                      allowFullScreen
                      loading="eager"
                      referrerPolicy="no-referrer-when-downgrade"
                    />
                  ) : (
                    <iframe
                      src={googleMapsEmbedUrl}
                      allowFullScreen
                      loading="eager"
                      referrerPolicy="no-referrer-when-downgrade"
                      onLoad={() => setGoogleMapsLoaded(true)}
                      onError={() => setGoogleMapsError(true)}
                    />
                  )}
                </div>
              )}
              <div className="map-buttons-bar">
                {/* Fullscreen toggle button */}
                <button
                  className={`map-action-btn fullscreen-toggle ${isMapFullscreen ? 'active' : ''}`}
                  onClick={toggleMapFullscreen}
                  title={isMapFullscreen ? "Exit fullscreen (Esc)" : "Fullscreen"}
                >
                  {isMapFullscreen ? (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="4 14 10 14 10 20"></polyline>
                      <polyline points="20 10 14 10 14 4"></polyline>
                      <line x1="14" y1="10" x2="21" y2="3"></line>
                      <line x1="3" y1="21" x2="10" y2="14"></line>
                    </svg>
                  ) : (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="15 3 21 3 21 9"></polyline>
                      <polyline points="9 21 3 21 3 15"></polyline>
                      <line x1="21" y1="3" x2="14" y2="10"></line>
                      <line x1="3" y1="21" x2="10" y2="14"></line>
                    </svg>
                  )}
                </button>
                {/* Share site button */}
                <button
                  className={`map-action-btn ${siteShareSuccess ? 'success' : ''}`}
                  onClick={handleShareSite}
                  title={siteShareSuccess ? "Copied!" : "Share site"}
                >
                  {siteShareSuccess ? (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4ade80" strokeWidth="2">
                      <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                  ) : (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="18" cy="5" r="3"></circle>
                      <circle cx="6" cy="12" r="3"></circle>
                      <circle cx="18" cy="19" r="3"></circle>
                      <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line>
                      <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line>
                    </svg>
                  )}
                </button>
                {/* Open in new tab */}
                {!isStandalone && (
                  <a
                    href={sitePopupUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="map-action-btn"
                    title="Open in new tab"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                      <polyline points="15 3 21 3 21 9"></polyline>
                      <line x1="10" y1="14" x2="21" y2="3"></line>
                    </svg>
                  </a>
                )}
                {/* Street View toggle button */}
                <button
                  className={`map-action-btn street-view-toggle ${showStreetView ? 'active' : ''}`}
                  onClick={() => setShowStreetView(!showStreetView)}
                  title={showStreetView ? "Show satellite" : "Show Street View"}
                >
                  {/* Pegman-style icon */}
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                    <circle cx="12" cy="4" r="2.5"/>
                    <path d="M12 8c-1.5 0-2.5.5-3 1.5L7 14l2 1-1 7h2l1.5-5h1l1.5 5h2l-1-7 2-1-2-4.5C14.5 8.5 13.5 8 12 8z"/>
                  </svg>
                </button>
                <div className="map-buttons-separator" />
                {/* Share Google Maps location */}
                <button
                  className="map-action-btn"
                  onClick={handleShareGoogleMaps}
                  title={shareSuccess ? "Copied!" : "Share Google Maps"}
                >
                  {shareSuccess ? (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4ade80" strokeWidth="2">
                      <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                  ) : (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polygon points="3 11 22 2 13 21 11 13 3 11"></polygon>
                    </svg>
                  )}
                </button>
                <a
                  href={googleMapsUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="map-action-btn"
                  title="Open in Google Maps"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                    <circle cx="12" cy="10" r="3"></circle>
                  </svg>
                </a>
              </div>
            </div>
          </div>
        </div>

        {/* Gallery Section - Fixed Height */}
        <div className={`popup-gallery-section ${isGalleryExpanded ? 'expanded' : ''}`}>
          {/* Collapse button - positioned absolutely in gallery */}
          {isGalleryExpanded && (
            <button
              className="gallery-collapse-btn"
              onClick={() => setIsGalleryExpanded(false)}
              title="Collapse"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="4 14 10 14 10 20"></polyline>
                <polyline points="20 10 14 10 14 4"></polyline>
                <line x1="14" y1="10" x2="21" y2="3"></line>
                <line x1="3" y1="21" x2="10" y2="14"></line>
              </svg>
            </button>
          )}

          {/* Expanded header with site name - draggable */}
          {isGalleryExpanded && (
            <div
              className="gallery-expanded-header"
              onMouseDown={!isStandalone ? handleTitleBarMouseDown : undefined}
              onDoubleClick={!isStandalone ? handleTitleBarDoubleClick : undefined}
              style={{ cursor: !isStandalone && windowState !== 'maximized' ? 'move' : undefined }}
            >
              <h2 className="gallery-expanded-title">{displaySite.title}</h2>
              <button
                className={`title-action-btn ${titleCopied ? 'copied' : ''}`}
                onMouseDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation()
                  navigator.clipboard.writeText(displaySite.title)
                  setTitleCopied(true)
                  setTimeout(() => setTitleCopied(false), 2000)
                }}
                title="Copy name"
              >
                {titleCopied ? (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                ) : (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                  </svg>
                )}
              </button>
            </div>
          )}

          {/* Gallery Tabs Header */}
          <div className="gallery-tabs">
            <button
              className={`gallery-tab ${activeGalleryTab === 'photos' ? 'active' : ''}`}
              onClick={() => setActiveGalleryTab('photos')}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                <circle cx="8.5" cy="8.5" r="1.5"></circle>
                <polyline points="21 15 16 10 5 21"></polyline>
              </svg>
              Photos
              <span className={`gallery-tab-count ${isLoadingImages ? 'loading' : ''}`}>
                {isLoadingImages ? '...' : photoItems.length}
              </span>
            </button>
            <button
              className={`gallery-tab ${activeGalleryTab === '3dmodels' ? 'active' : ''}`}
              onClick={() => setActiveGalleryTab('3dmodels')}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
                <line x1="12" y1="22.08" x2="12" y2="12"/>
              </svg>
              3D
              <span className={`gallery-tab-count ${sketchfabLoading ? 'loading' : ''}`}>
                {sketchfabLoading ? '...' : sketchfabItems.length}
              </span>
            </button>
            <button
              className={`gallery-tab ${activeGalleryTab === 'maps' ? 'active' : ''}`}
              onClick={() => setActiveGalleryTab('maps')}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                <line x1="3" y1="9" x2="21" y2="9"></line>
                <line x1="9" y1="21" x2="9" y2="9"></line>
              </svg>
              Maps
              <span className={`gallery-tab-count ${ancientMapsLoading ? 'loading' : ''}`}>
                {ancientMapsLoading ? '...' : mapItems.length}
              </span>
            </button>
            <button
              className={`gallery-tab ${activeGalleryTab === 'artifacts' ? 'active' : ''}`}
              onClick={() => setActiveGalleryTab('artifacts')}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
                <path d="M2 17l10 5 10-5"></path>
                <path d="M2 12l10 5 10-5"></path>
              </svg>
              Artifacts
              {artifactItems.length > 0 && <span className="gallery-tab-count">{artifactItems.length}</span>}
            </button>
            <button
              className={`gallery-tab ${activeGalleryTab === 'artworks' ? 'active' : ''}`}
              onClick={() => setActiveGalleryTab('artworks')}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="3" width="18" height="18" rx="2"></rect>
                <path d="M3 9h18"></path>
                <path d="M9 21V9"></path>
              </svg>
              Artworks
              {artworkItems.length > 0 && <span className="gallery-tab-count">{artworkItems.length}</span>}
            </button>
            <button
              className={`gallery-tab ${activeGalleryTab === 'texts' ? 'active' : ''}`}
              onClick={() => setActiveGalleryTab('texts')}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
                <line x1="16" y1="13" x2="8" y2="13"></line>
                <line x1="16" y1="17" x2="8" y2="17"></line>
              </svg>
              Texts
              {textItems.length > 0 && <span className="gallery-tab-count">{textItems.length}</span>}
            </button>
            <button
              className={`gallery-tab ${activeGalleryTab === 'myths' ? 'active' : ''}`}
              onClick={() => setActiveGalleryTab('myths')}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 3c.132 0 .263 0 .393 0a7.5 7.5 0 0 0 7.92 12.446a9 9 0 1 1 -8.313 -12.454z"></path>
                <path d="M17 4a2 2 0 0 0 2 2a2 2 0 0 0 -2 2a2 2 0 0 0 -2 -2a2 2 0 0 0 2 -2"></path>
              </svg>
              Myths
              {mythItems.length > 0 && <span className="gallery-tab-count">{mythItems.length}</span>}
            </button>

            {/* Expand button only shown when not expanded */}
            {!isGalleryExpanded && (
              <>
                <div className="gallery-tabs-spacer" />
                <button
                  className="gallery-expand-btn"
                  onClick={() => setIsGalleryExpanded(true)}
                  title="Expand"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="15 3 21 3 21 9"></polyline>
                    <polyline points="9 21 3 21 3 15"></polyline>
                    <line x1="21" y1="3" x2="14" y2="10"></line>
                    <line x1="3" y1="21" x2="10" y2="14"></line>
                  </svg>
                </button>
              </>
            )}
          </div>

          {/* Unified Gallery Content */}
          {renderGalleryContent()}
        </div>
      </div>
  )

  // Lightbox (rendered via portal, separate from popup)
  const lightbox = lightboxIndex !== null && lightboxItems.length > 0 && createPortal(
    <ImageLightbox
      images={lightboxItems}
      currentIndex={lightboxIndex}
      onClose={() => setLightboxIndex(null)}
      onNavigate={setLightboxIndex}
    />,
    document.body
  )

  // 3D Model viewer (rendered via portal, separate from popup)
  const modelViewer = modelViewerIndex !== null && sketchfabModels.length > 0 && createPortal(
    <ModelViewer
      models={sketchfabModels}
      currentIndex={modelViewerIndex}
      onClose={() => setModelViewerIndex(null)}
      onNavigate={setModelViewerIndex}
    />,
    document.body
  )

  // PIN auth modal (rendered via portal)
  const pinModal = showAdminPin && createPortal(
    <PinAuthModal
      isOpen={showAdminPin}
      onClose={() => setShowAdminPin(false)}
      onSuccess={() => {
        setEditedSite({ ...site })
        setIsAdminMode(true)
        setShowAdminPin(false)
      }}
      variant="admin"
    />,
    document.body
  )

  // In standalone mode, return content directly
  if (isStandalone) {
    return (
      <>
        {popupContent}
        {lightbox}
        {modelViewer}
        {pinModal}
      </>
    )
  }

  // In windowed mode, render popup directly via portal (no overlay blocking globe)
  return (
    <>
      {createPortal(popupContent, document.body)}
      {lightbox}
      {modelViewer}
      {pinModal}
    </>
  )
}
