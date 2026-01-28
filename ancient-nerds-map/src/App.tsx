import { useState, useEffect, useMemo, useCallback, useRef, lazy, Suspense } from 'react'
import Globe from './components/Globe'
import FilterPanel from './components/FilterPanel'
import { EmpirePolygonData, computeBoundingBox, isSiteInEmpirePolygons } from './utils/geometry'
import SitePopup from './components/SitePopup'
// Lazy-load modals for faster initial load
const ContributeModal = lazy(() => import('./components/ContributeModal'))
const DisclaimerModal = lazy(() => import('./components/DisclaimerModal'))
const PinAuthModal = lazy(() => import('./components/PinAuthModal'))
const AIAgentChatModal = lazy(() => import('./components/AIAgentChatModal'))
const DownloadManager = lazy(() => import('./components/DownloadManager'))
import { SiteData, fetchSites, getCurrentSites, addSourceSites, SOURCE_COLORS, getDefaultEnabledSourceIds, getSourceColor, getCategoryColor, getPeriodColor, setDataSourceError } from './data/sites'
import { DataStore } from './data/DataStore'
import { SourceLoader } from './services/SourceLoader'
import { ImageCache } from './services/ImageCache'
import { config } from './config'
import { fetchSiteImages, isWikipediaUrl, FetchSiteImagesResult } from './services/imageService'
import type { GalleryImage } from './components/ImageGallery'
import { OfflineProvider, useOffline } from './contexts/OfflineContext'
import { offlineFetch } from './services/OfflineFetch'

export type FilterMode = 'category' | 'age' | 'source' | 'country'

// Helper to get approximate year from period string for filtering
function periodToYear(period: string): number {
  switch (period) {
    case '< 4500 BC': return -5000
    case '4500 - 3000 BC': return -3750
    case '3000 - 1500 BC': return -2250
    case '1500 - 500 BC': return -1000
    case '500 BC - 1 AD': return -250
    case '1 - 500 AD': return 250
    case '500 - 1000 AD': return 750
    case '1000 - 1500 AD': return 1250
    case '1500+ AD': return 1750
    default: return 0
  }
}

// Extract country from location string (last part after comma, or whole string)
function extractCountry(location: string | undefined): string {
  if (!location) return 'Unknown'
  const parts = location.split(',')
  const country = parts[parts.length - 1].trim()
  return country || 'Unknown'
}

// Generate consistent color for a country using hash (returns hex for Globe compatibility)
function getCountryColor(country: string): string {
  // Hash the country name
  let hash = 0
  for (let i = 0; i < country.length; i++) {
    hash = country.charCodeAt(i) + ((hash << 5) - hash)
  }
  // Use golden ratio for better color distribution, convert to hex
  const hue = Math.abs((hash * 137.508) % 360)
  // Convert HSL to RGB then to hex
  const s = 0.7, l = 0.55
  const c = (1 - Math.abs(2 * l - 1)) * s
  const x = c * (1 - Math.abs((hue / 60) % 2 - 1))
  const m = l - c / 2
  let r = 0, g = 0, b = 0
  if (hue < 60) { r = c; g = x; b = 0 }
  else if (hue < 120) { r = x; g = c; b = 0 }
  else if (hue < 180) { r = 0; g = c; b = x }
  else if (hue < 240) { r = 0; g = x; b = c }
  else if (hue < 300) { r = x; g = 0; b = c }
  else { r = c; g = 0; b = x }
  const toHex = (n: number) => Math.round((n + m) * 255).toString(16).padStart(2, '0')
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`
}

// Normalize string for search: lowercase + remove diacritics
const normalizeForSearch = (str: string): string =>
  str.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')

// Haversine formula for calculating great-circle distance between two points
function haversineDistance(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371 // Earth radius in km
  const dLat = (lat2 - lat1) * Math.PI / 180
  const dLng = (lng2 - lng1) * Math.PI / 180
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
    Math.sin(dLng / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

interface SourceInfo {
  id: string
  name: string
  color: string
  count: number
}

interface SourceMeta {
  n: string
  c: string
  cnt: number
  primary?: boolean
}

// Check for standalone popup mode (opened via ?site= URL)
function getStandaloneSiteId(): string | null {
  const urlParams = new URLSearchParams(window.location.search)
  return urlParams.get('site')
}

// API response shape from /api/sites/{id}
interface ApiSiteDetail {
  id: string
  name: string
  lat: number
  lon: number
  sourceId: string
  type?: string
  periodStart?: number | null
  periodName?: string
  country?: string
  description?: string
  sourceUrl?: string
}

// Categorize period based on year (matches sites.ts logic)
function categorizePeriodFromYear(start: number | null | undefined): string {
  if (start === null || start === undefined) return 'Unknown'
  if (start < -4500) return '< 4500 BC'
  if (start < -3000) return '4500 - 3000 BC'
  if (start < -1500) return '3000 - 1500 BC'
  if (start < -500) return '1500 - 500 BC'
  if (start < 1) return '500 BC - 1 AD'
  if (start < 500) return '1 - 500 AD'
  if (start < 1000) return '500 - 1000 AD'
  if (start < 1500) return '1000 - 1500 AD'
  return '1500+ AD'
}

// Convert API detail response to SiteData - SINGLE SOURCE OF TRUTH
function apiDetailToSiteData(detail: ApiSiteDetail): SiteData {
  // Validate coordinates - null/undefined/NaN should not default to 0,0 (Atlantic Ocean)
  const hasValidLon = typeof detail.lon === 'number' && !isNaN(detail.lon)
  const hasValidLat = typeof detail.lat === 'number' && !isNaN(detail.lat)

  // Use coordinates only if both are valid numbers, otherwise use a placeholder
  // that will be obvious in the UI (center of map view, but flagged)
  const lon = hasValidLon ? detail.lon : NaN
  const lat = hasValidLat ? detail.lat : NaN

  return {
    id: detail.id,
    title: detail.name || 'Unknown Site',
    coordinates: [lon, lat],
    category: detail.type || 'Unknown',
    period: detail.periodName || categorizePeriodFromYear(detail.periodStart),
    periodStart: detail.periodStart,
    location: detail.country || '',
    description: detail.description || '',
    sourceId: detail.sourceId || 'unknown',
    sourceUrl: detail.sourceUrl,
  }
}

// Convert image search results to GalleryImage format (unified helper)
function convertToGalleryImages(imagesResult: { wikipedia: Array<{ thumb: string, full: string, title?: string, author?: string, authorUrl?: string, sourceUrl?: string, license?: string }> }): {
  wiki: GalleryImage[]
} {
  const wikiImages: GalleryImage[] = imagesResult.wikipedia.map(img => ({
    thumb: img.thumb,
    full: img.full,
    title: img.title,
    photographer: img.author,
    photographerUrl: img.authorUrl,
    wikimediaUrl: img.sourceUrl,
    license: img.license,
    source: 'wikipedia' as const,
  }))

  return { wiki: wikiImages }
}

function AppContent() {
  // Phone detection - block phones but allow tablets
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof window === 'undefined') return false

    // Check screen size - phones typically have smaller screens
    const isSmallScreen = window.innerWidth < 768 || window.innerHeight < 500

    // Check for phone user agents (NOT tablets - iPad, Tablet, etc. are allowed)
    const isPhone = /iPhone|iPod|Android.*Mobile|webOS|BlackBerry|IEMobile|Opera Mini|Windows Phone/i.test(navigator.userAgent)

    // Android without "Mobile" = tablet, Android with "Mobile" = phone
    // iPad user agent doesn't contain "Mobile"
    return isSmallScreen || isPhone
  })
  const [mobileWarningDismissed, setMobileWarningDismissed] = useState(false)

  useEffect(() => {
    const checkMobile = () => {
      const isSmallScreen = window.innerWidth < 768 || window.innerHeight < 500
      const isPhone = /iPhone|iPod|Android.*Mobile|webOS|BlackBerry|IEMobile|Opera Mini|Windows Phone/i.test(navigator.userAgent)
      setIsMobile(isSmallScreen || isPhone)
    }
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  // Offline mode state from context
  const { isOffline, setOfflineMode } = useOffline()

  // Check if we're in standalone mode (URL has ?site=xxx)
  const [standaloneSiteId] = useState(() => getStandaloneSiteId())

  const [sites, setSites] = useState<SiteData[]>([])
  const [filteredSites, setFilteredSites] = useState<SiteData[]>([])
  const [_categories, setCategories] = useState<string[]>([])
  const [selectedCategories, setSelectedCategories] = useState<string[]>([])
  const knownCategoriesRef = useRef<Set<string>>(new Set()) // Track all categories ever seen
  const [countries, setCountries] = useState<string[]>([])
  const [selectedCountries, setSelectedCountries] = useState<string[]>([])
  const knownCountriesRef = useRef<Set<string>>(new Set()) // Track all countries ever seen
  const [selectedSources, setSelectedSources] = useState<string[]>(['ancient_nerds'])
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState('')
  const searchDebounceRef = useRef<NodeJS.Timeout | null>(null)
  const [searchAllSources, setSearchAllSources] = useState(false)
  const [applyFiltersToSearch, setApplyFiltersToSearch] = useState(true)
  const [searchWithinProximity, setSearchWithinProximity] = useState(false)
  const [filterMode, setFilterMode] = useState<FilterMode>('age')
  const [ageRange, setAgeRange] = useState<[number, number]>([-5000, 1500])
  const [isLoading, setIsLoading] = useState(true) // Wait for default source before showing globe
  const [layersReady, setLayersReady] = useState(false) // Wait for coastlines/borders to load
  const [overlayFading, setOverlayFading] = useState(false) // Controls fade-out animation
  const [overlayRendered, setOverlayRendered] = useState(true) // Controls DOM presence after fade
  const [loadingStatus, setLoadingStatus] = useState('Initializing...') // Dynamic loading message
  const [downloadSpeed, setDownloadSpeed] = useState<string>('') // Download speed display
  const [downloadedMB, setDownloadedMB] = useState<number>(0) // Total MB downloaded
  const loadingStatusTimeoutRef = useRef<number | null>(null)
  const lastStatusChangeRef = useRef<number>(Date.now())
  const appStartTimeRef = useRef(Date.now())
  const MIN_SPLASH_DURATION = 3000  // 3 seconds minimum splash screen
  const speedTrackingRef = useRef({
    totalBytes: 0,
    lastTotalBytes: 0,
    lastUpdateTime: Date.now(),
    smoothedSpeed: 0, // Exponential moving average
    lastActivityTime: Date.now(),
  })
  const speedIntervalRef = useRef<number | null>(null)


  // Track download speed using PerformanceObserver with smoothing
  useEffect(() => {
    if (!overlayRendered) {
      if (speedIntervalRef.current) {
        clearInterval(speedIntervalRef.current)
        speedIntervalRef.current = null
      }
      return
    }

    const tracking = speedTrackingRef.current

    // Use PerformanceObserver to track resource loading
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (entry.entryType === 'resource') {
          const resourceEntry = entry as PerformanceResourceTiming
          const size = resourceEntry.transferSize || resourceEntry.encodedBodySize || 0
          if (size > 0) {
            tracking.totalBytes += size
            tracking.lastActivityTime = Date.now()
          }
        }
      }
    })

    try {
      observer.observe({ entryTypes: ['resource'] })
    } catch {
      // PerformanceObserver not supported
    }

    // Update display every 100ms with smoothing
    speedIntervalRef.current = window.setInterval(() => {
      const now = Date.now()
      const elapsed = (now - tracking.lastUpdateTime) / 1000 // seconds
      tracking.lastUpdateTime = now

      // Calculate instantaneous speed
      const bytesDiff = tracking.totalBytes - tracking.lastTotalBytes
      tracking.lastTotalBytes = tracking.totalBytes
      const instantSpeed = elapsed > 0 ? bytesDiff / elapsed : 0

      // Apply exponential moving average for smooth display
      // Alpha controls smoothing: lower = smoother but slower to react
      const alpha = 0.3
      if (instantSpeed > 0) {
        tracking.smoothedSpeed = alpha * instantSpeed + (1 - alpha) * tracking.smoothedSpeed
      } else {
        // Gradually decay speed when idle (but not too fast)
        const timeSinceActivity = now - tracking.lastActivityTime
        if (timeSinceActivity > 500) {
          tracking.smoothedSpeed *= 0.9 // Decay by 10% per interval
        }
      }

      // Update total downloaded
      const totalMB = tracking.totalBytes / (1024 * 1024)
      setDownloadedMB(totalMB)

      // Format and display speed
      const speed = tracking.smoothedSpeed
      if (speed >= 1024 * 1024) {
        setDownloadSpeed(`${(speed / (1024 * 1024)).toFixed(1)} MB/s`)
      } else if (speed >= 1024) {
        setDownloadSpeed(`${Math.round(speed / 1024)} KB/s`)
      } else if (speed > 10) {
        setDownloadSpeed(`${Math.round(speed)} B/s`)
      } else if (tracking.totalBytes > 0) {
        setDownloadSpeed('') // Hide when truly idle
      }
    }, 100)

    return () => {
      observer.disconnect()
      if (speedIntervalRef.current) {
        clearInterval(speedIntervalRef.current)
      }
    }
  }, [overlayRendered])

  // Update loading status with minimum 3 second display time to prevent flickering
  const updateLoadingStatus = useCallback((newStatus: string) => {
    const now = Date.now()
    const timeSinceLastChange = now - lastStatusChangeRef.current
    const minDisplayTime = 3000 // 3 seconds minimum

    if (timeSinceLastChange >= minDisplayTime) {
      // Enough time has passed, update immediately
      setLoadingStatus(newStatus)
      lastStatusChangeRef.current = now
    } else {
      // Schedule update after remaining time
      if (loadingStatusTimeoutRef.current) {
        clearTimeout(loadingStatusTimeoutRef.current)
      }
      const remainingTime = minDisplayTime - timeSinceLastChange
      loadingStatusTimeoutRef.current = window.setTimeout(() => {
        setLoadingStatus(newStatus)
        lastStatusChangeRef.current = Date.now()
      }, remainingTime)
    }
  }, [])
  const [loadingSources, setLoadingSources] = useState<Set<string>>(new Set()) // Sources currently loading
  const [backgroundSiteCount, _setBackgroundSiteCount] = useState(0) // Count of sites loading in background (for counter)
  // Multi-popup support: track all open popups by site ID
  interface OpenPopup {
    site: SiteData
    images: { wiki: GalleryImage[] } | null
    isMinimized: boolean
    isLoadingImages: boolean
  }
  const [openPopups, setOpenPopups] = useState<Map<string, OpenPopup>>(new Map())
  const [highlightedSiteId, setHighlightedSiteId] = useState<string | null>(null) // Site hovered in list
  const [isHoveringList, setIsHoveringList] = useState(false) // Hovering over search/proximity results
  const [listFrozenSiteIds, setListFrozenSiteIds] = useState<string[]>([]) // Sites frozen from click in list (supports multi-select with Ctrl)
  const [previousSelection, setPreviousSelection] = useState<string[]>([]) // For single-level undo
  const [canUndoSelection, setCanUndoSelection] = useState(false)
  const [redoSelection, setRedoSelection] = useState<string[]>([]) // For single-level redo
  const [canRedoSelection, setCanRedoSelection] = useState(false)
  const [isLoadingDetail, setIsLoadingDetail] = useState(false)
  const [flyToCoords, setFlyToCoords] = useState<[number, number] | null>(null)
  const [sourcesMeta, setSourcesMeta] = useState<Record<string, SourceMeta>>({})
  const [userLocation, setUserLocation] = useState<[number, number] | null>(null) // [lng, lat] from IP geolocation
  const [locationReady, setLocationReady] = useState(false) // True when location fetch completed (success or fail)

  // Image prefetch cache - stores promises for images being fetched for selected sites
  const imagePrefetchCache = useRef<Map<string, Promise<FetchSiteImagesResult>>>(new Map())

  // Proximity filter state
  const [proximityCenter, setProximityCenter] = useState<[number, number] | null>(null) // [lng, lat]
  const [proximityRadius, setProximityRadius] = useState(500) // km
  const [isSettingProximityOnGlobe, setIsSettingProximityOnGlobe] = useState(false)
  const [proximityHoverCoords, setProximityHoverCoords] = useState<[number, number] | null>(null) // [lng, lat]

  // Empire filter state (for "Within empires" checkbox)
  const [searchWithinEmpires, setSearchWithinEmpires] = useState(false)
  const [empirePolygons, setEmpirePolygons] = useState<Map<string, import('./utils/geometry').EmpirePolygonData>>(new Map())
  const [visibleEmpireIds, setVisibleEmpireIds] = useState<Set<string>>(new Set())
  const [empireSliderYears, setEmpireSliderYears] = useState<Record<string, number>>({})

  // Measurement tool state
  const [measureMode, setMeasureMode] = useState(false)
  // Yellow color palette for measurements
  const measurementColors = [
    '#FFD700', // Gold - warm bright yellow
    '#FFF44F', // Lemon yellow - cool bright
    '#FFCC00', // Amber yellow - deep rich
    '#F0E130', // Dandelion - vibrant
    '#FFE87C', // Jasmine - soft light yellow
  ]
  // Track used color indices to ensure no repeats until all used
  const [usedColorIndices, setUsedColorIndices] = useState<number[]>([])
  const getNextColor = () => {
    // Get available indices (not yet used)
    let available = measurementColors.map((_, i) => i).filter(i => !usedColorIndices.includes(i))
    // If all used, reset
    if (available.length === 0) {
      available = measurementColors.map((_, i) => i)
      setUsedColorIndices([])
    }
    // Pick random from available
    const randomIndex = available[Math.floor(Math.random() * available.length)]
    return { index: randomIndex, color: measurementColors[randomIndex] }
  }
  const [nextMeasurementColor, setNextMeasurementColor] = useState(() => measurementColors[Math.floor(Math.random() * measurementColors.length)])
  const [measurements, setMeasurements] = useState<Array<{
    id: string
    points: [[number, number], [number, number]] // [start, end] each [lng, lat]
    snapped: [boolean, boolean] // which points are snapped to sites
    color: string // unique color for this measurement
  }>>([])
  const [currentMeasurePoints, setCurrentMeasurePoints] = useState<Array<{ coords: [number, number], snapped: boolean }>>([]) // Points being placed
  const [selectedMeasurementId, setSelectedMeasurementId] = useState<string | null>(null)
  const [measureSnapEnabled, setMeasureSnapEnabled] = useState(true) // Enabled by default
  const [measureUnit, setMeasureUnit] = useState<'km' | 'miles'>('km')

  // DEL key handler to delete selected measurement
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Delete' && selectedMeasurementId) {
        setMeasurements(prev => prev.filter(m => m.id !== selectedMeasurementId))
        setSelectedMeasurementId(null)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [selectedMeasurementId])

  // Debounce search query to reduce globe updates while typing (200ms delay)
  useEffect(() => {
    if (searchDebounceRef.current) {
      clearTimeout(searchDebounceRef.current)
    }
    searchDebounceRef.current = setTimeout(() => {
      setDebouncedSearchQuery(searchQuery)
    }, 200)
    return () => {
      if (searchDebounceRef.current) {
        clearTimeout(searchDebounceRef.current)
      }
    }
  }, [searchQuery])

  // Random mode state - when true, only the random site dot is shown
  const [randomModeActive, setRandomModeActive] = useState(false)

  // Contribute modal state
  const [showContributeModal, setShowContributeModal] = useState(false)
  const [isContributeMapPickerActive, setIsContributeMapPickerActive] = useState(false)
  const [contributeHoverCoords, setContributeHoverCoords] = useState<[number, number] | null>(null) // [lng, lat] - live hover
  const [wasMapPickerCancelled, setWasMapPickerCancelled] = useState(false)

  // Disclaimer modal state
  const [showDisclaimerModal, setShowDisclaimerModal] = useState(false)

  // AI Agent modal state
  const [showPinModal, setShowPinModal] = useState(false)
  const [showAIChatModal, setShowAIChatModal] = useState(false)
  const [aiSessionToken, setAiSessionToken] = useState<string | null>(null)

  // Download manager modal state
  const [showDownloadManager, setShowDownloadManager] = useState(false)

  // Additional sources loading - track which sources have been loaded
  const [loadedSourceIds, setLoadedSourceIds] = useState<Set<string>>(new Set())
  const [_nonDefaultSourceIds, setNonDefaultSourceIds] = useState<string[]>([])

  // Debounce ref for batching site updates (prevents stutter during rapid source loading)
  const pendingSiteUpdateRef = useRef<number | null>(null)

  // Stable function to update sites from DataStore (called after sources load)
  const updateSitesFromDataStore = useCallback(() => {
    // Cancel any pending update
    if (pendingSiteUpdateRef.current) {
      clearTimeout(pendingSiteUpdateRef.current)
    }
    // Schedule update after short delay (batches rapid source loads)
    pendingSiteUpdateRef.current = window.setTimeout(() => {
      pendingSiteUpdateRef.current = null
      const allSites = getCurrentSites()
      setSites(allSites)

      const allCategories = [...new Set(allSites.map(s => s.category).filter(Boolean))].sort()
      setCategories(allCategories)
      setSelectedCategories(prev => {
        const trulyNewCats = allCategories.filter(c => !knownCategoriesRef.current.has(c))
        trulyNewCats.forEach(c => knownCategoriesRef.current.add(c))
        return trulyNewCats.length > 0 ? [...prev, ...trulyNewCats] : prev
      })

      const allCountries = [...new Set(allSites.map(s => extractCountry(s.location)).filter(c => c !== 'Unknown'))].sort()
      setCountries(allCountries)
      setSelectedCountries(prev => {
        const trulyNewCountries = allCountries.filter(c => !knownCountriesRef.current.has(c))
        trulyNewCountries.forEach(c => knownCountriesRef.current.add(c))
        return trulyNewCountries.length > 0 ? [...prev, ...trulyNewCountries] : prev
      })
    }, 50) // 50ms debounce
  }, [])

  // Handle live hover coords from contribute map picker (like proximity)
  const handleContributeMapHover = useCallback((coords: [number, number] | null) => {
    setContributeHoverCoords(coords)
  }, [])

  // Handle cancel from coordinate picker (X button)
  const handleContributeMapCancel = useCallback(() => {
    setWasMapPickerCancelled(true)
    setIsContributeMapPickerActive(false)
  }, [])

  // Clear picked coords
  const handleClearContributeCoords = useCallback(() => {
    setContributeHoverCoords(null)
  }, [])

  // AI Agent handlers
  const handleAIAgentClick = useCallback(() => {
    if (aiSessionToken) {
      // Already authenticated, open chat directly
      setShowAIChatModal(true)
    } else {
      // Need to authenticate first
      setShowPinModal(true)
    }
  }, [aiSessionToken])

  const handlePinSuccess = useCallback((token: string) => {
    setAiSessionToken(token)
    setShowPinModal(false)
    setShowAIChatModal(true)
  }, [])

  const handleAIHighlightSites = useCallback((siteIds: string[]) => {
    // Use the existing selection mechanism to highlight sites
    setListFrozenSiteIds(siteIds)
  }, [])

  // Async image loader - runs in background after popup opens
  const loadImagesForPopup = useCallback(async (siteData: SiteData) => {
    const wikipediaUrl = siteData.sourceUrl && isWikipediaUrl(siteData.sourceUrl)
      ? siteData.sourceUrl : undefined

    let images: { wiki: GalleryImage[] } = { wiki: [] }

    try {
      const cachedPromise = imagePrefetchCache.current.get(siteData.id)
      let imagesResult: FetchSiteImagesResult

      if (cachedPromise) {
        imagesResult = await cachedPromise
      } else {
        imagesResult = await fetchSiteImages(siteData.title, {
          wikipediaUrl,
          location: siteData.location,
          limit: 12,
        })
      }
      images = convertToGalleryImages(imagesResult)
    } catch (err) {
      console.warn('Failed to load images:', err)
    }

    // Preload hero image
    const heroUrl = images.wiki[0]?.full
    if (heroUrl) {
      try {
        const cachedUrl = await ImageCache.preloadAndCache(heroUrl)
        if (images.wiki[0]) {
          images.wiki[0] = { ...images.wiki[0], full: cachedUrl }
        }
      } catch (err) {
        console.warn('Failed to cache hero image:', err)
      }
    }

    // Update popup with images (if still open)
    setOpenPopups(prev => {
      const next = new Map(prev)
      const existing = next.get(siteData.id)
      if (existing) {
        next.set(siteData.id, { ...existing, images, isLoadingImages: false })
      }
      return next
    })
  }, [])

  // Opens popup IMMEDIATELY, starts image loading in background
  const openSitePopup = useCallback(async (siteData: SiteData) => {
    // Open popup immediately with loading state
    setOpenPopups(prev => {
      const next = new Map(prev)
      if (!next.has(siteData.id)) {
        next.set(siteData.id, {
          site: siteData,
          images: null,
          isMinimized: false,
          isLoadingImages: true
        })
      }
      return next
    })
    setIsLoadingDetail(false)

    // Start async image loading (non-blocking)
    loadImagesForPopup(siteData)
  }, [loadImagesForPopup])

  // Fetch site details and open popup
  const handleSiteClick = useCallback(async (site: SiteData | null) => {
    if (!site) return

    // If popup already open for this site, don't open another
    if (openPopups.has(site.id)) return

    setIsLoadingDetail(true)

    try {
      // Fetch full site details (fast API call)
      const response = await offlineFetch(`${config.api.baseUrl}/sites/${site.id}`)
      let siteData = site

      if (response.ok) {
        const detail = await response.json()
        if (detail && !detail.error) {
          // Use shared helper, but preserve any existing data from static load
          const apiData = apiDetailToSiteData(detail)
          siteData = {
            ...site,           // Keep static data (coordinates, title, etc. already correct)
            ...apiData,        // Override with API data
            // Prefer static data for fields that might be richer there
            title: site.title || apiData.title,
            category: site.category || apiData.category,
          }
        }
      }

      // Use unified popup opener
      openSitePopup(siteData)
    } catch (error) {
      console.warn('Could not fetch site data:', error)
      // Fallback: open with basic data
      openSitePopup(site)
    }
  }, [openSitePopup, openPopups])

  // Close a popup by site ID
  const closePopup = useCallback((siteId: string) => {
    setOpenPopups(prev => {
      const next = new Map(prev)
      next.delete(siteId)
      return next
    })
  }, [])

  // Update minimized state for a popup
  const setPopupMinimized = useCallback((siteId: string, isMinimized: boolean) => {
    setOpenPopups(prev => {
      const next = new Map(prev)
      const popup = next.get(siteId)
      if (popup) {
        next.set(siteId, { ...popup, isMinimized })
      }
      return next
    })
  }, [])

  useEffect(() => {
    // Standalone mode: fetch only the single site, skip everything else
    if (standaloneSiteId) {
      const loadStandaloneSite = async () => {
        try {
          // Initialize DataStore to load source metadata (needed for display names)
          // This loads sources.json which populates getSourceInfo()
          await fetchSites()

          // Fetch site details directly from API
          const response = await offlineFetch(`${config.api.baseUrl}/sites/${standaloneSiteId}`)
          if (!response.ok) {
            setIsLoading(false)
            return
          }
          const detail = await response.json()
          if (!detail || detail.error) {
            setIsLoading(false)
            return
          }

          // Build site data from API response using shared helper
          const siteData = apiDetailToSiteData(detail)

          // Keep loading state while hero image loads
          setIsLoadingDetail(true)
          await openSitePopup(siteData) // Same unified function as normal mode!
          setIsLoading(false)
        } catch (error) {
          console.error('Failed to load site:', error)
          setIsLoading(false)
        }
      }
      loadStandaloneSite()
      return
    }

    // Normal mode: progressive loading
    // Phase 1: Load default source first, then show globe with dots
    const loadData = async () => {
      // IP geolocation - MUST complete before Globe renders
      // Uses same logic as FilterPanel proximity (which works)
      let detectedLocation: [number, number] | null = null
      try {
        const res = await fetch('https://ipwho.is/')
        if (res.ok) {
          const data = await res.json()
          if (data?.success && typeof data.latitude === 'number' && typeof data.longitude === 'number') {
            detectedLocation = [data.longitude, data.latitude]
          }
        }
      } catch { /* try fallback */ }

      // Fallback to geojs.io
      if (!detectedLocation) {
        try {
          const res = await fetch('https://get.geojs.io/v1/ip/geo.json')
          if (res.ok) {
            const data = await res.json()
            const lat = parseFloat(data?.latitude)
            const lng = parseFloat(data?.longitude)
            if (!isNaN(lat) && !isNaN(lng)) {
              detectedLocation = [lng, lat]
            }
          }
        } catch { /* use default */ }
      }

      // Set location state BEFORE anything else
      if (detectedLocation) {
        setUserLocation(detectedLocation)
      }
      setLocationReady(true)

      // Fetch sites and sources in parallel with location
      updateLoadingStatus('Loading archaeological sites...')
      let data: SiteData[] = []
      try {
        data = await fetchSites()
        setSites(data)

        // Get source metadata from DataStore (already loaded in parallel with sites)
        const sources = DataStore.getSources()
        const sourcesMetaMap: Record<string, SourceMeta> = {}
        for (const source of sources) {
          sourcesMetaMap[source.id] = {
            n: source.name,
            c: source.color,
            cnt: source.recordCount,
            primary: source.isPrimary
          }
        }
        setSourcesMeta(sourcesMetaMap)
      } catch (error) {
        console.error("Failed to fetch sites:", error)
        setDataSourceError()  // Set error state for red LED indicator
        setSites([])
        setIsLoading(false)
        return
      }

      // Get all source IDs from DataStore
      const allSourceIds = DataStore.getSources().map(s => s.id)

      updateLoadingStatus('Preparing globe view...')

      const uniqueCategories = [...new Set(data.map(s => s.category).filter(Boolean))].sort()
      setCategories(uniqueCategories)
      setSelectedCategories(uniqueCategories)
      // Track as known so they won't be re-added if user deselects
      uniqueCategories.forEach(c => knownCategoriesRef.current.add(c))

      const uniqueCountries = [...new Set(data.map(s => extractCountry(s.location)).filter(c => c !== 'Unknown'))].sort()
      setCountries(uniqueCountries)
      setSelectedCountries(uniqueCountries)
      // Track as known so they won't be re-added if user deselects
      uniqueCountries.forEach(c => knownCountriesRef.current.add(c))

      const defaultSourceIds = getDefaultEnabledSourceIds()
      setSelectedSources(defaultSourceIds)
      // Mark default sources as already loaded (they were loaded via fetchSites)
      setLoadedSourceIds(new Set(defaultSourceIds))

      // Store non-default sources for later loading (when user clicks "Load Sources")
      const nonDefaultSources = allSourceIds.filter(id => !defaultSourceIds.includes(id))
      setNonDefaultSourceIds(nonDefaultSources)

      // NOW show the globe (default source is loaded)
      setIsLoading(false)
      // Note: Additional sources are NOT loaded automatically - user must click "Load Sources" button
    }
    loadData()
  }, [standaloneSiteId, openSitePopup])

  // Load specific sources when user clicks on them or "Load All"
  const handleLoadSources = useCallback((sourceIdsToLoad: string[]) => {
    // Filter out already loaded or currently loading sources
    const toLoad = sourceIdsToLoad.filter(id =>
      !loadedSourceIds.has(id) && !loadingSources.has(id)
    )
    if (toLoad.length === 0) return

    // Mark as loading
    setLoadingSources(prev => {
      const next = new Set(prev)
      toLoad.forEach(id => next.add(id))
      return next
    })

    SourceLoader.loadSources(toLoad, {
      onSourceLoaded: (sourceId, loadedSites) => {
        // Add sites to DataStore
        addSourceSites(sourceId, loadedSites)
        // Extract new categories and countries from the loaded sites BEFORE updating sites state
        // This prevents the filter from removing sites whose categories/countries aren't in selected yet
        const newCategories = [...new Set(loadedSites.map(s => s.type).filter((t): t is string => Boolean(t)))]
        const newCountries = [...new Set(loadedSites.map(s => {
          if (!s.location) return 'Unknown'
          const parts = s.location.split(',')
          return parts[parts.length - 1].trim() || 'Unknown'
        }).filter((c): c is string => c !== 'Unknown'))]

        // Add ALL categories from this source to selected (not just new ones)
        // This ensures sites aren't filtered out when loading new sources
        setSelectedCategories(prev => {
          const missing = newCategories.filter(c => !prev.includes(c))
          newCategories.forEach(c => knownCategoriesRef.current.add(c))
          return missing.length > 0 ? [...prev, ...missing] : prev
        })

        // Add ALL countries from this source to selected (not just new ones)
        // This ensures sites aren't filtered out when loading new sources
        setSelectedCountries(prev => {
          const missing = newCountries.filter(c => !prev.includes(c))
          newCountries.forEach(c => knownCountriesRef.current.add(c))
          return missing.length > 0 ? [...prev, ...missing] : prev
        })

        // Update state
        setLoadedSourceIds(prev => new Set([...prev, sourceId]))
        setLoadingSources(prev => {
          const next = new Set(prev)
          next.delete(sourceId)
          return next
        })
        setSelectedSources(prev =>
          prev.includes(sourceId) ? prev : [...prev, sourceId]
        )

        // Update sites from DataStore immediately when each source loads
        updateSitesFromDataStore()
      },
      onSourceError: (sourceId) => {
        setLoadingSources(prev => {
          const next = new Set(prev)
          next.delete(sourceId)
          return next
        })
      },
      onComplete: () => {
        // All queued sources have finished loading
      }
    })
  }, [loadedSourceIds, loadingSources, updateSitesFromDataStore])

  // Compute source info - include ALL known sources, not just loaded ones
  const sources: SourceInfo[] = useMemo(() => {
    const result: SourceInfo[] = []

    // Include ALL sources from metadata that have sites (cnt > 0)
    // Use meta.cnt (total count from sources.json) for display and sorting
    for (const [sourceId, meta] of Object.entries(sourcesMeta)) {
      // Skip sources with no sites (placeholder entries)
      if (!meta?.cnt || meta.cnt === 0) continue

      result.push({
        id: sourceId,
        name: meta?.n || sourceId.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
        color: meta?.c || SOURCE_COLORS[sourceId] || SOURCE_COLORS.default || '#9ca3af',
        count: meta.cnt
      })
    }

    return result.sort((a, b) => {
      // Always put ancient_nerds (primary source) at the top
      if (a.id === 'ancient_nerds') return -1
      if (b.id === 'ancient_nerds') return 1
      // Then sort by count (descending)
      return b.count - a.count
    })
  }, [sourcesMeta])

  // Create source color map for Globe (uses same colors as FilterPanel)
  const sourceColorMap = useMemo(() => {
    const map: Record<string, string> = {}
    for (const source of sources) {
      map[source.id] = source.color
    }
    return map
  }, [sources])

  // Create source name map
  const sourceNameMap = useMemo(() => {
    const map: Record<string, string> = {}
    for (const source of sources) {
      map[source.id] = source.name
    }
    return map
  }, [sources])

  // Create country color map for Globe (use all countries for consistent colors)
  const countryColorMap = useMemo(() => {
    const map: Record<string, string> = {}
    for (const country of countries) {
      map[country] = getCountryColor(country)
    }
    return map
  }, [countries])

  // Filter countries by active sources for display
  const countriesFromActiveSources = useMemo(() => {
    const activeSites = sites.filter(s => selectedSources.includes(s.sourceId))
    const activeCountries = [...new Set(activeSites.map(s => extractCountry(s.location)).filter(c => c !== 'Unknown'))].sort()
    return activeCountries
  }, [sites, selectedSources])

  // Filter categories by active sources for display
  const categoriesFromActiveSources = useMemo(() => {
    const activeSites = sites.filter(s => selectedSources.includes(s.sourceId))
    const activeCategories = [...new Set(activeSites.map(s => s.category).filter(Boolean))].sort()
    return activeCategories
  }, [sites, selectedSources])

  // Cross-filtered available categories (respects country + age filters)
  const availableCategories = useMemo(() => {
    let filtered = sites.filter(s => selectedSources.includes(s.sourceId))

    // Apply country filter
    if (selectedCountries.length > 0 && selectedCountries.length < countriesFromActiveSources.length) {
      filtered = filtered.filter(s => selectedCountries.includes(extractCountry(s.location)))
    }

    // Apply age filter
    if (ageRange[0] > -5000 || ageRange[1] < 1500) {
      filtered = filtered.filter(s => {
        const year = s.periodStart ?? periodToYear(s.period)
        return year >= ageRange[0] && year <= ageRange[1]
      })
    }

    return [...new Set(filtered.map(s => s.category).filter(Boolean))].sort()
  }, [sites, selectedSources, selectedCountries, countriesFromActiveSources, ageRange])

  // Cross-filtered available countries (respects category + age filters)
  const availableCountries = useMemo(() => {
    let filtered = sites.filter(s => selectedSources.includes(s.sourceId))

    // Apply category filter
    if (selectedCategories.length > 0 && selectedCategories.length < categoriesFromActiveSources.length) {
      filtered = filtered.filter(s => selectedCategories.includes(s.category))
    }

    // Apply age filter
    if (ageRange[0] > -5000 || ageRange[1] < 1500) {
      filtered = filtered.filter(s => {
        const year = s.periodStart ?? periodToYear(s.period)
        return year >= ageRange[0] && year <= ageRange[1]
      })
    }

    return [...new Set(filtered.map(s => extractCountry(s.location)).filter(c => c !== 'Unknown'))].sort()
  }, [sites, selectedSources, selectedCategories, categoriesFromActiveSources, ageRange])

  // Generate search results for dropdown (uses debounced query to reduce updates while typing)
  const searchResults = useMemo(() => {
    if (!debouncedSearchQuery.trim()) return []

    const query = normalizeForSearch(debouncedSearchQuery)
    let sitesToSearch = searchAllSources ? sites : sites.filter(s => selectedSources.includes(s.sourceId))

    // Apply filters to search results only if "Apply filters" is checked
    if (applyFiltersToSearch) {
      // Apply age range filter
      if (ageRange[0] > -5000 || ageRange[1] < 1500) {
        sitesToSearch = sitesToSearch.filter(site => {
          const year = site.periodStart ?? periodToYear(site.period)
          return year >= ageRange[0] && year <= ageRange[1]
        })
      }
      // Apply category filter (always, not just in category mode)
      if (selectedCategories.length < categoriesFromActiveSources.length && selectedCategories.length > 0) {
        sitesToSearch = sitesToSearch.filter(site => selectedCategories.includes(site.category))
      }
      // Apply country filter (always, not just in country mode)
      if (selectedCountries.length > 0 && selectedCountries.length < countries.length) {
        sitesToSearch = sitesToSearch.filter(site => {
          const country = extractCountry(site.location)
          return selectedCountries.includes(country)
        })
      }
    }

    // Apply proximity filter when "Search within proximity" is checked and proximity is set
    if (searchWithinProximity && proximityCenter) {
      const [centerLng, centerLat] = proximityCenter
      sitesToSearch = sitesToSearch.filter(site => {
        const [siteLng, siteLat] = site.coordinates
        const distance = haversineDistance(centerLat, centerLng, siteLat, siteLng)
        return distance <= proximityRadius
      })
    }

    // Apply empire filter when "Within empires" is checked and empires are visible
    if (searchWithinEmpires && visibleEmpireIds.size > 0) {
      const activeEmpirePolygons: EmpirePolygonData[] = []
      for (const empireId of visibleEmpireIds) {
        const currentYear = empireSliderYears[empireId]
        if (currentYear !== undefined) {
          const polygonData = empirePolygons.get(`${empireId}:${currentYear}`)
          if (polygonData) {
            activeEmpirePolygons.push(polygonData)
          }
        }
      }

      if (activeEmpirePolygons.length > 0) {
        sitesToSearch = sitesToSearch.filter(site => {
          // Use periodStart if available, fall back to period string
          const siteYear = site.periodStart ?? periodToYear(site.period)
          for (const empireData of activeEmpirePolygons) {
            if (siteYear > empireData.year) {
              continue
            }
            if (isSiteInEmpirePolygons(site.coordinates, [empireData])) {
              return true
            }
          }
          return false
        })
      }
    }

    // Filter and sort by relevance
    const matchingSites = sitesToSearch
      .filter(site =>
        normalizeForSearch(site.title).includes(query) ||
        (site.location && normalizeForSearch(site.location).includes(query)) ||
        (site.description && normalizeForSearch(site.description).includes(query))
      )
      .map(site => {
        const titleNorm = normalizeForSearch(site.title)
        // Calculate relevance score (higher = more relevant)
        let score = 0
        if (titleNorm === query) {
          score = 100 // Exact title match
        } else if (titleNorm.startsWith(query)) {
          score = 80 // Title starts with query
        } else if (titleNorm.includes(query)) {
          score = 60 // Title contains query
        } else if (site.location && normalizeForSearch(site.location).includes(query)) {
          score = 40 // Location contains query
        } else {
          score = 20 // Description contains query
        }
        return { site, score }
      })
      .sort((a, b) => b.score - a.score) // Sort by score descending
      .map(({ site }) => site)

    return matchingSites
      .slice(0, 100)
      .map(site => {
        // Ensure category and period have values (fallback to 'Unknown' for display)
        const category = site.category || 'Unknown'
        const period = site.period || 'Unknown'
        return {
          id: site.id,
          title: site.title,
          category,
          categoryColor: getCategoryColor(category),
          location: site.location,
          period,
          periodColor: getPeriodColor(period),
          sourceName: sourceNameMap[site.sourceId] || site.sourceId,
          sourceColor: getSourceColor(site.sourceId),
          sourceUrl: site.sourceUrl,
        }
      })
  }, [debouncedSearchQuery, searchAllSources, sites, selectedSources, sourceNameMap, sourceColorMap, applyFiltersToSearch, ageRange, selectedCategories, categoriesFromActiveSources, selectedCountries, countries, filterMode, searchWithinProximity, proximityCenter, proximityRadius, searchWithinEmpires, visibleEmpireIds, empireSliderYears, empirePolygons])

  // Handle search result selection
  const handleSearchResultSelect = useCallback((siteId: string, openPopup: boolean) => {
    const site = sites.find(s => s.id === siteId)
    if (site) {
      // Force re-fly by clearing first, then setting coordinates
      setFlyToCoords(null)
      setTimeout(() => setFlyToCoords(site.coordinates), 10)
      if (openPopup) {
        handleSiteClick(site)
      }
    }
  }, [sites, handleSiteClick])

  // Handle random site selection - respects all search options (sources, filters, proximity)
  const handleRandomSite = useCallback(() => {
    // Start with sites from selected sources, or all sites if searchAllSources is enabled
    let availableSites = searchAllSources
      ? sites
      : sites.filter(s => selectedSources.includes(s.sourceId))

    // Apply filters if "Apply filters" is checked
    if (applyFiltersToSearch) {
      // Apply age range filter
      if (ageRange[0] > -5000 || ageRange[1] < 1500) {
        availableSites = availableSites.filter(site => {
          const year = site.periodStart ?? periodToYear(site.period)
          return year >= ageRange[0] && year <= ageRange[1]
        })
      }
      // Apply category filter
      if (selectedCategories.length < categoriesFromActiveSources.length && selectedCategories.length > 0) {
        availableSites = availableSites.filter(site => selectedCategories.includes(site.category))
      }
      // Apply country filter
      if (selectedCountries.length > 0 && selectedCountries.length < countries.length) {
        availableSites = availableSites.filter(site => {
          const country = extractCountry(site.location)
          return selectedCountries.includes(country)
        })
      }
    }

    // Apply proximity filter if "Search within proximity" is checked and proximity is set
    if (searchWithinProximity && proximityCenter) {
      const [centerLng, centerLat] = proximityCenter
      availableSites = availableSites.filter(site => {
        const [siteLng, siteLat] = site.coordinates
        const distance = haversineDistance(centerLat, centerLng, siteLat, siteLng)
        return distance <= proximityRadius
      })
    }

    // Apply empire filter when "Within empires" is checked and empires are visible
    if (searchWithinEmpires && visibleEmpireIds.size > 0) {
      const activeEmpirePolygons: EmpirePolygonData[] = []
      for (const empireId of visibleEmpireIds) {
        const currentYear = empireSliderYears[empireId]
        if (currentYear !== undefined) {
          const polygonData = empirePolygons.get(`${empireId}:${currentYear}`)
          if (polygonData) {
            activeEmpirePolygons.push(polygonData)
          }
        }
      }

      if (activeEmpirePolygons.length > 0) {
        availableSites = availableSites.filter(site => {
          // Use periodStart if available, fall back to period string
          const siteYear = site.periodStart ?? periodToYear(site.period)
          for (const empireData of activeEmpirePolygons) {
            if (siteYear > empireData.year) {
              continue
            }
            if (isSiteInEmpirePolygons(site.coordinates, [empireData])) {
              return true
            }
          }
          return false
        })
      }
    }

    if (availableSites.length === 0) return

    // Pick a random site and put its name in the search field
    const randomIndex = Math.floor(Math.random() * availableSites.length)
    const randomSite = availableSites[randomIndex]
    setSearchQuery(randomSite.title)

    // Fly to the site and select it to show the tooltip
    // Save current selection for undo before Random changes it
    setPreviousSelection(listFrozenSiteIds)
    setFlyToCoords(null)

    // Enable random mode to hide all other dots
    setRandomModeActive(true)

    // Force state change by clearing first, then setting new value
    // This ensures the ring/tooltip effect triggers on every click
    setListFrozenSiteIds([])
    setTimeout(() => {
      setListFrozenSiteIds([randomSite.id])
      setFlyToCoords(randomSite.coordinates)
    }, 50)

    setCanUndoSelection(true)
  }, [sites, selectedSources, searchAllSources, applyFiltersToSearch, ageRange, selectedCategories, categoriesFromActiveSources, selectedCountries, countries, searchWithinProximity, proximityCenter, proximityRadius, listFrozenSiteIds, searchWithinEmpires, visibleEmpireIds, empireSliderYears, empirePolygons])

  // Selection wrapper with undo tracking
  const updateSelection = useCallback((newIds: string[]) => {
    setPreviousSelection(listFrozenSiteIds)
    setListFrozenSiteIds(newIds)
    setCanUndoSelection(true)
    setCanRedoSelection(false) // Clear redo when new selection is made
    setRandomModeActive(false) // Exit random mode on manual selection
  }, [listFrozenSiteIds])

  // Pre-fetch images when sites are selected (before popup opens)
  // This makes popup opening much faster for pre-selected sites
  useEffect(() => {
    listFrozenSiteIds.forEach(siteId => {
      // Skip if already prefetching or cached
      if (imagePrefetchCache.current.has(siteId)) return

      const site = sites.find(s => s.id === siteId)
      if (!site) return

      // Get Wikipedia URL for image fetching
      const wikipediaUrl = site.sourceUrl && isWikipediaUrl(site.sourceUrl)
        ? site.sourceUrl : undefined

      // Start prefetching in background - fetch metadata AND cache hero image
      const fetchPromise = fetchSiteImages(site.title, {
        wikipediaUrl,
        location: site.location,
        limit: 12,
      }).then(async (result) => {
        // Also prefetch and cache the hero image immediately
        const heroUrl = result.wikipedia[0]?.full
        if (heroUrl) {
          await ImageCache.preloadAndCache(heroUrl).catch(() => {})
        }
        return result
      }).catch(() => {
        return { wikipedia: [], europeana: [] }
      })

      imagePrefetchCache.current.set(siteId, fetchPromise)
    })
  }, [listFrozenSiteIds, sites])

  // Pre-fetch images for top search results (cold start optimization)
  // This reduces popup load time for sites appearing in search
  useEffect(() => {
    // Only prefetch top 5 results to avoid excessive requests
    const topResults = searchResults.slice(0, 5)

    topResults.forEach(site => {
      // Skip if already prefetching or cached
      if (imagePrefetchCache.current.has(site.id)) return

      // Get Wikipedia URL for image fetching
      const wikipediaUrl = site.sourceUrl && isWikipediaUrl(site.sourceUrl)
        ? site.sourceUrl : undefined

      // Start prefetching in background
      const fetchPromise = fetchSiteImages(site.title, {
        wikipediaUrl,
        location: site.location,
        limit: 12,
      }).then(async (result) => {
        // Also prefetch and cache the hero image immediately
        const heroUrl = result.wikipedia[0]?.full
        if (heroUrl) {
          await ImageCache.preloadAndCache(heroUrl).catch(() => {})
        }
        return result
      }).catch(() => {
        return { wikipedia: [], europeana: [] }
      })

      imagePrefetchCache.current.set(site.id, fetchPromise)
    })
  }, [searchResults])

  const undoSelection = useCallback(() => {
    if (!canUndoSelection) return
    setRedoSelection(listFrozenSiteIds) // Save current for redo
    setListFrozenSiteIds(previousSelection)
    setCanUndoSelection(false)
    setCanRedoSelection(true)
  }, [canUndoSelection, previousSelection, listFrozenSiteIds])

  const redoSelectionFn = useCallback(() => {
    if (!canRedoSelection) return
    setPreviousSelection(listFrozenSiteIds) // Save current for undo
    setListFrozenSiteIds(redoSelection)
    setCanUndoSelection(true)
    setCanRedoSelection(false)
  }, [canRedoSelection, redoSelection, listFrozenSiteIds])

  // Default age range constant
  const DEFAULT_AGE_RANGE: [number, number] = [-5000, 1500]

  // Reset all filters to defaults
  const handleResetAllFilters = useCallback(() => {
    // Reset sources first (to Ancient Nerds only)
    setSelectedSources(['ancient_nerds'])
    setAgeRange(DEFAULT_AGE_RANGE)
    // Compute categories/countries from default source (ancient_nerds)
    const defaultSourceSites = sites.filter(s => s.sourceId === 'ancient_nerds')
    const defaultCategories = [...new Set(defaultSourceSites.map(s => s.category).filter(Boolean))].sort()
    const defaultCountries = [...new Set(defaultSourceSites.map(s => extractCountry(s.location)).filter(c => c !== 'Unknown'))].sort()
    setSelectedCategories(defaultCategories)
    setSelectedCountries(defaultCountries)
  }, [sites])

  // Handle category change with auto-centering
  const handleCategoryChange = useCallback((newCategories: string[]) => {
    const prevCategories = selectedCategories
    setSelectedCategories(newCategories)

    // Find newly added categories
    const addedCategories = newCategories.filter(c => !prevCategories.includes(c))

    // Only fly when exactly ONE category is added (not "select all" which adds many)
    const isAddingSingleCategory = addedCategories.length === 1

    // Special case: user isolated a single category from a larger selection
    const isIsolatingSingleCategory = newCategories.length === 1 &&
      prevCategories.length > 1 &&
      prevCategories.includes(newCategories[0])

    if (isAddingSingleCategory || isIsolatingSingleCategory) {
      const targetCategory = isAddingSingleCategory
        ? addedCategories[0]
        : newCategories[0]

      // Find all sites with this category from active sources
      const categorySites = sites.filter(s =>
        selectedSources.includes(s.sourceId) &&
        s.category === targetCategory
      )

      if (categorySites.length > 0) {
        // Compute centroid of all sites in this category
        const sumLng = categorySites.reduce((sum, s) => sum + s.coordinates[0], 0)
        const sumLat = categorySites.reduce((sum, s) => sum + s.coordinates[1], 0)
        const centerLng = sumLng / categorySites.length
        const centerLat = sumLat / categorySites.length

        // Fly to category center
        setFlyToCoords(null)
        setTimeout(() => setFlyToCoords([centerLng, centerLat]), 10)
      }
    }
  }, [selectedCategories, sites, selectedSources])

  // Handle country change with auto-centering
  const handleCountryChange = useCallback((newCountries: string[]) => {
    const prevCountries = selectedCountries
    setSelectedCountries(newCountries)

    // Find newly added countries
    const addedCountries = newCountries.filter(c => !prevCountries.includes(c))

    // Only fly when exactly ONE country is added (not "select all" which adds many)
    const isAddingSingleCountry = addedCountries.length === 1

    // Special case: user isolated a single country from a larger selection
    // (e.g., clicked a country when all were selected - this deselects others)
    const isIsolatingSingleCountry = newCountries.length === 1 &&
      prevCountries.length > 1 &&
      prevCountries.includes(newCountries[0])

    if (isAddingSingleCountry || isIsolatingSingleCountry) {
      // Determine target country
      const targetCountry = isAddingSingleCountry
        ? addedCountries[0]
        : newCountries[0]  // The isolated country

      // Find all sites in the selected country from active sources
      const countrySites = sites.filter(s =>
        selectedSources.includes(s.sourceId) &&
        extractCountry(s.location) === targetCountry
      )

      if (countrySites.length > 0) {
        // Compute centroid of all sites in this country
        const sumLng = countrySites.reduce((sum, s) => sum + s.coordinates[0], 0)
        const sumLat = countrySites.reduce((sum, s) => sum + s.coordinates[1], 0)
        const centerLng = sumLng / countrySites.length
        const centerLat = sumLat / countrySites.length

        // Fly to country center
        setFlyToCoords(null)
        setTimeout(() => setFlyToCoords([centerLng, centerLat]), 10)
      }
    }
  }, [selectedCountries, sites, selectedSources])

  // Calculate proximity status for each site (inside or outside radius)
  // Only uses SET center (not hover) - hover dimming is handled directly in Globe for performance
  const sitesWithProximity = useMemo(() => {
    const result = (() => {
      if (!proximityCenter) {
        return filteredSites.map(site => ({ ...site, isInsideProximity: true }))
      }
      const [centerLng, centerLat] = proximityCenter
      return filteredSites.map(site => {
        const [siteLng, siteLat] = site.coordinates
        const distance = haversineDistance(centerLat, centerLng, siteLat, siteLng)
        return { ...site, isInsideProximity: distance <= proximityRadius }
      })
    })()
    // Mark sites as selected or not based on frozen selection
    if (listFrozenSiteIds.length > 0) {
      return result.map(site => ({
        ...site,
        isSelected: listFrozenSiteIds.includes(site.id)
      }))
    }
    return result
  }, [filteredSites, proximityCenter, proximityRadius, listFrozenSiteIds])

  // Track popup IDs with stable reference - only changes when actual keys change, not when isMinimized changes
  const prevOpenPopupIdsRef = useRef<string[]>([])
  const openPopupIds = useMemo(() => {
    const currentIds = Array.from(openPopups.keys()).sort()
    const prevIds = prevOpenPopupIdsRef.current
    // Only return new array if keys actually changed
    if (currentIds.length === prevIds.length && currentIds.every((id, i) => id === prevIds[i])) {
      return prevIds
    }
    prevOpenPopupIdsRef.current = currentIds
    return currentIds
  }, [openPopups])

  // Selection is now independent of popup state
  // Tooltips only show for explicitly selected sites, not for sites with open popups
  const combinedFrozenSiteIds = listFrozenSiteIds

  // Handle proximity set from globe click
  const handleProximitySet = useCallback((coords: [number, number]) => {
    setProximityCenter(coords)
    setIsSettingProximityOnGlobe(false) // Auto-disable after setting
  }, [])

  // Handle proximity hover coordinates from globe
  const handleProximityHover = useCallback((coords: [number, number] | null) => {
    setProximityHoverCoords(coords)
  }, [])

  // Auto fly to proximity center when it changes
  useEffect(() => {
    if (proximityCenter) {
      setFlyToCoords(null)
      setTimeout(() => setFlyToCoords(proximityCenter), 10)
    }
  }, [proximityCenter])

  // Handle empire visibility changes from Globe
  const handleVisibleEmpiresChange = useCallback((empireIds: Set<string>) => {
    setVisibleEmpireIds(empireIds)
    // Clear polygon data for empires that are no longer visible
    setEmpirePolygons(prev => {
      const next = new Map(prev)
      for (const key of next.keys()) {
        const empireId = key.split(':')[0]
        if (!empireIds.has(empireId)) {
          next.delete(key)
        }
      }
      return next
    })
    // Note: We don't reset searchWithinEmpires here - the checkbox stays checked
    // but disabled when no empires are visible, so it re-applies when empires are enabled again
  }, [])

  // Handle empire year changes from Globe
  const handleEmpireYearsChange = useCallback((years: Record<string, number>) => {
    setEmpireSliderYears(years)
  }, [])

  // Handle empire polygon data loaded from Globe
  const handleEmpirePolygonsLoaded = useCallback((empireId: string, year: number, features: any[]) => {
    const bbox = computeBoundingBox(features)
    setEmpirePolygons(prev => {
      const next = new Map(prev)
      next.set(`${empireId}:${year}`, { empireId, year, bbox, features })
      return next
    })
  }, [])

  // Generate proximity results (sites inside the radius) for display in results panel
  const proximityResults = useMemo(() => {
    if (!proximityCenter) return []

    return sitesWithProximity
      .filter(site => site.isInsideProximity)
      .slice(0, 100)
      .map(site => {
        // Ensure category and period have values (fallback to 'Unknown' for display)
        const category = site.category || 'Unknown'
        const period = site.period || 'Unknown'
        return {
          id: site.id,
          title: site.title,
          category,
          categoryColor: getCategoryColor(category),
          location: site.location,
          period,
          periodColor: getPeriodColor(period),
          sourceName: sourceNameMap[site.sourceId] || site.sourceId,
          sourceColor: getSourceColor(site.sourceId),
        }
      })
  }, [sitesWithProximity, proximityCenter, sourceNameMap])

  useEffect(() => {
    let result = sites
    const isSearching = debouncedSearchQuery.trim().length > 0

    // When searching with "search all sources" enabled, skip source filter
    const skipSourceFilter = searchAllSources && isSearching

    // Filter by source (unless searching all sources)
    if (!skipSourceFilter) {
      if (selectedSources.length === 0) {
        // No sources selected = show nothing
        result = []
      } else {
        result = result.filter(site => selectedSources.includes(site.sourceId))
      }
    }

    // Apply category/country/age filters:
    // - Always when NOT searching
    // - Only when "Apply filters" is checked while searching
    const shouldApplyFilters = !isSearching || applyFiltersToSearch

    if (shouldApplyFilters) {
      // Filter by age range (using periodStart if available)
      if (ageRange[0] > -5000 || ageRange[1] < 1500) {
        result = result.filter(site => {
          const year = site.periodStart ?? periodToYear(site.period)
          return year >= ageRange[0] && year <= ageRange[1]
        })
      }

      // Filter by category
      if (selectedCategories.length < categoriesFromActiveSources.length) {
        result = result.filter(site => selectedCategories.includes(site.category))
      }

      // Filter by country
      if (selectedCountries.length > 0 && selectedCountries.length < countriesFromActiveSources.length) {
        result = result.filter(site => {
          const country = extractCountry(site.location)
          return selectedCountries.includes(country)
        })
      }
    }

    // Apply proximity filter when "Within proximity" is checked and proximity is set
    // (only applies during search - proximity results panel handles non-search case)
    if (isSearching && searchWithinProximity && proximityCenter) {
      const [centerLng, centerLat] = proximityCenter
      result = result.filter(site => {
        const [siteLng, siteLat] = site.coordinates
        const distance = haversineDistance(centerLat, centerLng, siteLat, siteLng)
        return distance <= proximityRadius
      })
    }

    // Apply empire filter when "Within empires" is checked and empires are visible
    // Filter sites to only those inside active empire boundaries AND from appropriate time period
    if (searchWithinEmpires && visibleEmpireIds.size > 0) {
      // Collect polygon data for all visible empires at their current year
      const activeEmpirePolygons: EmpirePolygonData[] = []
      for (const empireId of visibleEmpireIds) {
        const currentYear = empireSliderYears[empireId]
        if (currentYear !== undefined) {
          const polygonData = empirePolygons.get(`${empireId}:${currentYear}`)
          if (polygonData) {
            activeEmpirePolygons.push(polygonData)
          }
        }
      }

      if (activeEmpirePolygons.length > 0) {
        result = result.filter(site => {
          // Use periodStart if available, fall back to period string
          const siteYear = site.periodStart ?? periodToYear(site.period)
          // Temporal check: site must have existed by the empire's displayed year
          // Check against ALL active empires - site just needs to match ONE
          for (const empireData of activeEmpirePolygons) {
            // Site must have existed by this empire's displayed year
            if (siteYear > empireData.year) {
              continue // Site is too young for this empire
            }
            // Spatial check: site must be inside this empire's boundaries
            if (isSiteInEmpirePolygons(site.coordinates, [empireData])) {
              return true
            }
          }
          return false
        })
      }
    }

    // Filter by search query when searching (uses debounced query to reduce globe updates)
    // Keep filter applied even with frozen selection - only dim non-selected search results, not show all dots
    if (isSearching) {
      const query = normalizeForSearch(debouncedSearchQuery)
      result = result.filter(site =>
        normalizeForSearch(site.title).includes(query) ||
        normalizeForSearch(site.location).includes(query) ||
        (site.description && normalizeForSearch(site.description).includes(query))
      )

      // Fly to first search result (only when no selection - don't override user's clicked site)
      if (result.length > 0 && listFrozenSiteIds.length === 0) {
        setFlyToCoords(result[0].coordinates)
      }
    } else {
      // Clear flyTo when search is cleared
      setFlyToCoords(null)
    }

    setFilteredSites(result)
  }, [sites, selectedSources, selectedCategories, categoriesFromActiveSources, selectedCountries, countriesFromActiveSources, debouncedSearchQuery, searchAllSources, ageRange, applyFiltersToSearch, searchWithinProximity, proximityCenter, proximityRadius, searchWithinEmpires, visibleEmpireIds, empireSliderYears, empirePolygons, listFrozenSiteIds])

  // Handle loading overlay fade-out transition with minimum display time
  const loadingComplete = !isLoading && layersReady
  useEffect(() => {
    if (loadingComplete && overlayRendered && !overlayFading) {
      // Check if minimum display time has passed
      const elapsed = Date.now() - appStartTimeRef.current
      const remaining = MIN_SPLASH_DURATION - elapsed

      if (remaining > 0) {
        // Wait for remaining time before fading
        const timer = setTimeout(() => {
          setOverlayFading(true)
        }, remaining)
        return () => clearTimeout(timer)
      } else {
        // Minimum time already passed, fade immediately
        setOverlayFading(true)
      }
    }
  }, [loadingComplete, overlayRendered, overlayFading])

  // Standalone mode: show only the popup in a minimal container
  if (standaloneSiteId) {
    if (isLoading || isLoadingDetail) {
      return (
        <div className="standalone-popup-container">
          <div className="standalone-popup-loading">
            <div className="loading-spinner" />
            <div className="loading-text">Loading site...</div>
          </div>
        </div>
      )
    }

    // Get the standalone popup from openPopups map
    const standalonePopup = openPopups.get(standaloneSiteId)
    if (!standalonePopup) {
      return (
        <div className="standalone-popup-container">
          <div className="standalone-popup-error">
            <h2>Site not found</h2>
            <a href="/" className="standalone-back-btn">Back to Map</a>
          </div>
        </div>
      )
    }

    return (
      <div className="standalone-popup-container">
        <SitePopup
          site={standalonePopup.site}
          onClose={() => {
            // In standalone mode, closing goes back to main map
            window.location.href = '/'
          }}
          prefetchedImages={standalonePopup.images}
          isStandalone={true}
          isLoadingImages={false}
        />
      </div>
    )
  }

  // Mobile users see desktop-only message (unless dismissed)
  if (isMobile && !mobileWarningDismissed) {
    return (
      <div className="mobile-overlay">
        <div className="mobile-overlay-content">
          <div className="mobile-logo-main">ANCIENT NERDS</div>
          <div className="mobile-logo-sub">RESEARCH PLATFORM</div>
          <div className="mobile-message">
            This interactive 3D globe experience is optimized for desktop browsers.
          </div>
          <div className="mobile-hint">
            For the best experience, please visit on a computer with a larger screen.
          </div>
          <button
            className="mobile-continue-btn"
            onClick={() => setMobileWarningDismissed(true)}
          >
            Continue Anyway
          </button>
        </div>
      </div>
    )
  }

  return (
    <>
      {/* Main loading overlay - shown until sites AND layers are ready, then fades out */}
      {overlayRendered && (
        <div
          className={`loading-overlay${overlayFading ? ' fading' : ''}`}
          onTransitionEnd={() => overlayFading && setOverlayRendered(false)}
        >
          <div className="loading-spinner-container">
            <div className="loading-spinner" />
            <img src="/an-logo.svg" alt="Ancient Nerds" className="loading-logo" />
          </div>
          <div className="loading-text">{layersReady ? 'READY' : loadingStatus.toUpperCase()}</div>
          {(downloadSpeed || downloadedMB > 0) && (
            <div className="loading-speed">
              {downloadSpeed && <span>{downloadSpeed}</span>}
              {downloadedMB > 0.1 && <span className="loading-total">{downloadedMB.toFixed(1)} MB</span>}
            </div>
          )}
          <div className="loading-hint">For best performance, enable hardware acceleration in your browser</div>
        </div>
      )}
      {/* Loading cursor overlay for site detail loading */}
      {isLoadingDetail && (
        <div className="loading-cursor-overlay">
          <div className="loading-cursor-spinner" />
        </div>
      )}
      {locationReady && <Globe
        sites={sitesWithProximity}
        splashDone={overlayFading}
        filterMode={filterMode}
        sourceColors={sourceColorMap}
        countryColors={countryColorMap}
        highlightedSiteId={highlightedSiteId}
        isHoveringList={isHoveringList || listFrozenSiteIds.length > 0}
        listFrozenSiteIds={combinedFrozenSiteIds}
        openPopupIds={openPopupIds}
        onSiteClick={handleSiteClick}
        onTooltipClick={(site) => {
          // If popup is open and minimized, restore it
          const existingPopup = openPopups.get(site.id)
          if (existingPopup) {
            if (existingPopup.isMinimized) {
              setPopupMinimized(site.id, false)
            }
            // Popup already open, just bring focus (nothing else to do)
            return
          }
          // No popup open, open a new one
          handleSiteClick(site)
        }}
        onSiteSelect={(siteId, ctrlKey) => {
          if (siteId === null) {
            // Click on empty space - deselect all
            updateSelection([])
            setHighlightedSiteId(null) // Clear highlight from minimized bar clicks
            return
          }
          // Check if site has an open popup - don't toggle deselect for these
          const hasOpenPopup = openPopups.has(siteId)
          if (ctrlKey) {
            // Ctrl+click: toggle selection (but don't deselect if popup is open)
            if (listFrozenSiteIds.includes(siteId) && !hasOpenPopup) {
              updateSelection(listFrozenSiteIds.filter(x => x !== siteId))
            } else if (!listFrozenSiteIds.includes(siteId)) {
              updateSelection([...listFrozenSiteIds, siteId])
            }
            // If site has open popup and already selected, keep it selected (no-op)
          } else {
            // Normal click: select this site (don't toggle deselect if popup is open)
            if (listFrozenSiteIds.length === 1 && listFrozenSiteIds[0] === siteId && !hasOpenPopup) {
              updateSelection([]) // Toggle off only if no open popup
            } else {
              updateSelection([siteId]) // Select this site
            }
          }
        }}
        flyTo={flyToCoords}
        isLoading={isLoadingDetail}
        proximity={{
          center: proximityCenter,
          radius: proximityRadius,
          isSettingOnGlobe: isSettingProximityOnGlobe,
        }}
        onProximitySet={handleProximitySet}
        onProximityHover={handleProximityHover}
        initialPosition={userLocation}
        onLayersReady={() => {
          updateLoadingStatus('Map layers ready!')
          setLayersReady(true)
        }}
        onContributeClick={() => setShowContributeModal(true)}
        onAIAgentClick={handleAIAgentClick}
        onDisclaimerClick={() => setShowDisclaimerModal(true)}
        isContributeMapPickerActive={isContributeMapPickerActive}
        onContributeMapHover={handleContributeMapHover}
        onContributeMapConfirm={() => {
          setWasMapPickerCancelled(false)
          setIsContributeMapPickerActive(false)
        }}
        onContributeMapCancel={handleContributeMapCancel}
        canUndoSelection={canUndoSelection}
        onUndoSelection={undoSelection}
        canRedoSelection={canRedoSelection}
        onRedoSelection={redoSelectionFn}
        measureMode={measureMode}
        measurements={measurements}
        currentMeasurePoints={currentMeasurePoints}
        selectedMeasurementId={selectedMeasurementId}
        measureSnapEnabled={measureSnapEnabled}
        measureUnit={measureUnit}
        randomModeActive={randomModeActive}
        searchWithinProximity={searchWithinProximity}
        currentMeasurementColor={nextMeasurementColor}
        onMeasurePointAdd={(coords, snapped) => {
          if (currentMeasurePoints.length >= 1) {
            // Complete measurement - use the current color
            const newMeasurement = {
              id: `measure-${Date.now()}`,
              points: [currentMeasurePoints[0].coords, coords] as [[number, number], [number, number]],
              snapped: [currentMeasurePoints[0].snapped, snapped] as [boolean, boolean],
              color: nextMeasurementColor
            }
            setMeasurements([...measurements, newMeasurement])
            setCurrentMeasurePoints([]) // Reset for next measurement
            setSelectedMeasurementId(newMeasurement.id) // Select the new one
            // Pick next random color (avoiding recently used)
            const { index, color } = getNextColor()
            setUsedColorIndices(prev => [...prev, index])
            setNextMeasurementColor(color)
          } else {
            setCurrentMeasurePoints([{ coords, snapped }])
          }
        }}
        onMeasurementSelect={(id) => setSelectedMeasurementId(id)}
        onMeasurementDelete={(id) => {
          setMeasurements(measurements.filter(m => m.id !== id))
          if (selectedMeasurementId === id) setSelectedMeasurementId(null)
        }}
        onAgeRangeSync={(range) => setAgeRange(range)}
        onVisibleEmpiresChange={handleVisibleEmpiresChange}
        onEmpireYearsChange={handleEmpireYearsChange}
        onEmpirePolygonsLoaded={handleEmpirePolygonsLoaded}
        onOfflineClick={() => setShowDownloadManager(true)}
        isOffline={isOffline}
      />}
      <FilterPanel
        categories={categoriesFromActiveSources}
        selectedCategories={selectedCategories}
        availableCategories={availableCategories}
        countries={countriesFromActiveSources}
        selectedCountries={selectedCountries}
        availableCountries={availableCountries}
        countryColors={countryColorMap}
        sources={sources}
        selectedSources={selectedSources}
        loadingSources={loadingSources}
        searchQuery={searchQuery}
        searchAllSources={searchAllSources}
        searchResults={searchResults}
        filterMode={filterMode}
        ageRange={ageRange}
        onCategoryChange={handleCategoryChange}
        onCountryChange={handleCountryChange}
        onSourceChange={setSelectedSources}
        onSearchChange={setSearchQuery}
        onSearchAllSourcesChange={setSearchAllSources}
        applyFiltersToSearch={applyFiltersToSearch}
        onApplyFiltersToSearchChange={setApplyFiltersToSearch}
        searchWithinProximity={searchWithinProximity}
        onSearchWithinProximityChange={setSearchWithinProximity}
        onSearchResultSelect={handleSearchResultSelect}
        onRandomSite={handleRandomSite}
        onFilterModeChange={setFilterMode}
        onAgeRangeChange={setAgeRange}
        totalSites={sites.length + backgroundSiteCount}
        filteredCount={filteredSites.length}
        proximityCenter={proximityCenter}
        proximityRadius={proximityRadius}
        isSettingProximityOnGlobe={isSettingProximityOnGlobe}
        onProximityCenterChange={setProximityCenter}
        onProximityRadiusChange={setProximityRadius}
        onSetProximityOnGlobeChange={setIsSettingProximityOnGlobe}
        proximityResults={proximityResults}
        proximityHoverCoords={proximityHoverCoords}
        onSiteHover={(id) => {
          setHighlightedSiteId(id)
          setIsHoveringList(id !== null)
        }}
        onSiteListClick={(id, ctrlKey) => {
          if (id === null) {
            // Clear all selections
            updateSelection([])
            setHighlightedSiteId(null)
          } else if (ctrlKey) {
            // Ctrl+click: toggle selection
            updateSelection(
              listFrozenSiteIds.includes(id)
                ? listFrozenSiteIds.filter(x => x !== id)
                : [...listFrozenSiteIds, id]
            )
            // Show tooltip for clicked site
            setHighlightedSiteId(id)
            setIsHoveringList(true)
          } else {
            // Normal click: replace selection
            const isDeselecting = listFrozenSiteIds.length === 1 && listFrozenSiteIds[0] === id
            updateSelection(isDeselecting ? [] : [id])
            // Show tooltip for clicked site (or clear if deselecting)
            setHighlightedSiteId(isDeselecting ? null : id)
            setIsHoveringList(!isDeselecting)
          }
        }}
        selectedSiteIds={listFrozenSiteIds}
        onResetAllFilters={handleResetAllFilters}
        defaultAgeRange={DEFAULT_AGE_RANGE}
        loadedSourceIds={loadedSourceIds}
        onLoadSources={handleLoadSources}
        searchWithinEmpires={searchWithinEmpires}
        onSearchWithinEmpiresChange={setSearchWithinEmpires}
        hasVisibleEmpires={visibleEmpireIds.size > 0}
        measureMode={measureMode}
        onMeasureModeChange={(enabled) => {
          setMeasureMode(enabled)
          if (!enabled) {
            setCurrentMeasurePoints([])
          }
        }}
        measurements={measurements}
        currentMeasurePoints={currentMeasurePoints}
        selectedMeasurementId={selectedMeasurementId}
        measureSnapEnabled={measureSnapEnabled}
        onMeasureSnapChange={setMeasureSnapEnabled}
        onMeasurementSelect={(id) => {
          setSelectedMeasurementId(id)
          // Fly to measurement midpoint when selecting
          if (id) {
            const measurement = measurements.find(m => m.id === id)
            if (measurement) {
              const [start, end] = measurement.points
              const midLng = (start[0] + end[0]) / 2
              const midLat = (start[1] + end[1]) / 2
              setFlyToCoords(null)
              setTimeout(() => setFlyToCoords([midLng, midLat]), 10)
            }
          }
        }}
        onMeasurementDelete={(id) => {
          setMeasurements(measurements.filter(m => m.id !== id))
          if (selectedMeasurementId === id) setSelectedMeasurementId(null)
        }}
        onClearAllMeasurements={() => {
          setMeasurements([])
          setCurrentMeasurePoints([])
          setSelectedMeasurementId(null)
        }}
        measureUnit={measureUnit}
        onMeasureUnitChange={setMeasureUnit}
        onActiveTabChange={(tab) => {
          // Measurement is only active when in measure tab
          setMeasureMode(tab === 'measure')
          // Clear in-progress measurement when leaving measure tab
          if (tab !== 'measure') {
            setCurrentMeasurePoints([])
          }
        }}
      />
      {/* Render all open popups */}
      {Array.from(openPopups.entries()).map(([siteId, popup]) => {
        // Calculate stack index for minimized popups
        const minimizedPopups = Array.from(openPopups.values()).filter(p => p.isMinimized)
        const minimizedIndex = minimizedPopups.findIndex(p => p.site.id === siteId)

        return (
          <SitePopup
            key={siteId}
            site={popup.site}
            prefetchedImages={popup.images}
            isLoadingImages={popup.isLoadingImages}
            onClose={() => closePopup(siteId)}
            onMinimizedChange={(isMin) => setPopupMinimized(siteId, isMin)}
            minimizedStackIndex={popup.isMinimized ? minimizedIndex : -1}
            onSetProximity={setProximityCenter}
            onFlyTo={(coords) => {
              setFlyToCoords(null)
              setTimeout(() => setFlyToCoords(coords), 10)
            }}
            onHighlight={setHighlightedSiteId}
            onSelect={(id, ctrlKey) => {
              if (ctrlKey) {
                // Ctrl+click: toggle in selection
                updateSelection(
                  listFrozenSiteIds.includes(id)
                    ? listFrozenSiteIds.filter(x => x !== id)
                    : [...listFrozenSiteIds, id]
                )
              } else {
                // Normal click: replace selection
                updateSelection([id])
              }
            }}
            onSiteUpdate={async (id, updated) => {
              // Immediately update local state for instant feedback
              setSites(prev => prev.map(s => s.id === id ? updated : s))
              // Also refresh from API to ensure persistence
              try {
                const freshData = await fetchSites()
                setSites(freshData)
              } catch {
                // Refresh from API failed, local state is still updated
              }
            }}
          />
        )
      })}

      {/* Lazy-loaded modals wrapped in Suspense for faster initial load */}
      <Suspense fallback={null}>
        {/* Contribute Modal - always mounted to preserve form state */}
        <ContributeModal
          isOpen={showContributeModal}
          onClose={() => {
            setShowContributeModal(false)
            setIsContributeMapPickerActive(false)
            setContributeHoverCoords(null)
            setWasMapPickerCancelled(false)
          }}
          onEnableMapPicker={() => {
            setWasMapPickerCancelled(false)
            setIsContributeMapPickerActive(true)
          }}
          isMapPickerActive={isContributeMapPickerActive}
          hoverCoords={contributeHoverCoords}
          onClearCoords={handleClearContributeCoords}
          wasMapPickerCancelled={wasMapPickerCancelled}
        />

        {/* Disclaimer Modal */}
        <DisclaimerModal
          isOpen={showDisclaimerModal}
          onClose={() => setShowDisclaimerModal(false)}
        />

        {/* Download Manager Modal */}
        <DownloadManager
          isOpen={showDownloadManager}
          onClose={() => setShowDownloadManager(false)}
          sources={sources}
          isOffline={isOffline}
          onToggleOffline={() => setOfflineMode(!isOffline)}
        />

        {/* AI Agent Modals */}
        <PinAuthModal
          isOpen={showPinModal}
          onClose={() => setShowPinModal(false)}
          onSuccess={handlePinSuccess}
        />

        <AIAgentChatModal
          isOpen={showAIChatModal}
          onClose={() => setShowAIChatModal(false)}
          sessionToken={aiSessionToken || ''}
          onHighlightSites={handleAIHighlightSites}
          onFlyToSite={(coords) => {
            setFlyToCoords(null)
            setTimeout(() => setFlyToCoords(coords), 10)
          }}
        />
      </Suspense>
    </>
  )
}

/**
 * App wrapper that provides offline context to all components
 */
function App() {
  return (
    <OfflineProvider>
      <AppContent />
    </OfflineProvider>
  )
}

export default App
