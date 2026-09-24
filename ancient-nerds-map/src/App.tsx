import { useState, useEffect, useLayoutEffect, useMemo, useCallback, useRef, lazy, Suspense } from 'react'
import { track } from './analytics'
import { errorProps } from './analytics/boot'
import {
  createGlobeEndingLatch,
  installGlobeAbandon,
  loadPhase,
  reportGateChoice,
  reportWebglLost,
  type GateChoice,
  type StartItem,
} from './analytics/globeAbandon'
import Globe, { type AppBackgroundTasks } from './components/Globe'
import GlobeErrorBoundary from './components/GlobeErrorBoundary'
import GlobeErrorScreen from './components/GlobeErrorScreen'
import GlobeUnsupported from './components/GlobeUnsupported'
import PhoneGate from './components/PhoneGate'
import FilterPanel from './components/FilterPanel'
import { EmpirePolygonData, computeBoundingBox, isSiteInEmpirePolygons } from './utils/geometry'
import SitePopup, { EmpirePopupData } from './components/SitePopup'
import LazyErrorBoundary from './components/LazyErrorBoundary'
import { EMPIRES } from './config/empireData'
import { isPhoneOrSmallScreen } from './utils/deviceTier'
import { checkGlobeSupport } from './utils/globeSupport'
import { GlobeStartError, LIVE_PHASE, failurePhase } from './utils/globeStartError'
import { lookupFocusLocation } from './utils/focusLocation'
import { lookupIpLocation } from './utils/ipLocation'
import { START_STALL_MS, createStallWatchdog, type StallWatchdog } from './utils/loadWatchdog'

// Lazy-load modals for faster initial load
const ContributeModal = lazy(() => import('./components/ContributeModal'))
const DisclaimerModal = lazy(() => import('./components/DisclaimerModal'))
const LyraChatModal = lazy(() => import('./components/LyraChatModal'))
const DownloadManager = lazy(() => import('./components/DownloadManager'))
const NewsFeedPanel = lazy(() => import('./components/NewsFeedPanel'))
import { SiteData, fetchSites, getCurrentSites, addSourceSites, SOURCE_COLORS, getDefaultEnabledSourceIds, getSourceColor, getCategoryColor, getPeriodColor, setDataSourceError, loadSiteDetails, mergeSiteDetails, withSiteDetails, globeSiteFields } from './data/sites'
import { DataStore } from './data/DataStore'
import { SourceLoader } from './services/SourceLoader'
import { config } from './config'
import { apiDetailToSiteData } from './utils/siteApi'
import { BRAND_ASSETS } from './constants/brand'
import { OfflineProvider, useOffline } from './contexts/OfflineContext'
import { AuthProvider } from './contexts/AuthContext'
import { offlineFetch } from './services/OfflineFetch'
import { ensureServiceWorkerActive, serviceWorkerTask } from './pwa/registerServiceWorker'
import { isDemoMode, registerAppDemoApi } from './utils/demoApi'
import { normalizeForSearch, periodToYear, extractCountry } from './utils/searchUtils'
import { haversineDistance } from './utils/geoMath'
import { reportAchievementEvent } from './utils/cardApi'
import AchievementToast from './components/AchievementToast'
import { useSiteSearch } from './hooks/useSiteSearch'
import { useGlobeScreenEnding, type ScreenEnding } from './hooks/useGlobeScreenEnding'
import { useGlobeBehindGate } from './hooks/useGlobeBehindGate'
import { useGlobeReady } from './hooks/useGlobeReady'

export type FilterMode = 'category' | 'age' | 'source' | 'country'

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

interface SourceInfo {
  id: string
  name: string
  color: string
  count: number
  primary?: boolean
  priority: number
  category?: string
}

interface SourceMeta {
  n: string
  c: string
  cnt: number
  pri?: boolean   // is_primary from DB
  p?: number      // priority from DB (lower = higher)
  on?: boolean    // enabled_by_default
  cat?: string    // category from DB
}

// Check for standalone popup mode (opened via ?site= URL)
function getStandaloneSiteId(): string | null {
  const urlParams = new URLSearchParams(window.location.search)
  return urlParams.get('site')
}

// Check for focus mode (opened via a #focus= or ?focus= URL)
// Loads the globe normally, then centers on the site and opens its popup.
// Hrefs on the SEO pages use the fragment form (globeUrlForSite, brand.ts)
// so crawlers see one /globe.html instead of one URL per site; the query
// form stays valid for window.open() callers and every link already out
// there.
function getFocusSiteId(): string | null {
  const fromQuery = new URLSearchParams(window.location.search).get('focus')
  if (fromQuery) return fromQuery
  return new URLSearchParams(window.location.hash.replace(/^#/, '')).get('focus')
}

// Check for coordinate fly-to (opened via ?lat=&lon= from Lyra coord links)
function getInitialCoords(): { coords: [number, number]; proximity: boolean } | null {
  const urlParams = new URLSearchParams(window.location.search)
  const lat = parseFloat(urlParams.get('lat') || '')
  const lon = parseFloat(urlParams.get('lon') || '')
  if (!isNaN(lat) && !isNaN(lon)) return { coords: [lon, lat], proximity: urlParams.get('proximity') === '1' }
  return null
}


function AppContent() {
  // Phone detection - block phones but allow tablets
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof window === 'undefined') return false
    return isPhoneOrSmallScreen()
  })
  const [mobileWarningDismissed, setMobileWarningDismissed] = useState(false)

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(isPhoneOrSmallScreen())
    }
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  // Offline mode state from context
  const { isOffline, setOfflineMode } = useOffline()

  // Check if we're in standalone mode (URL has ?site=xxx)
  const [standaloneSiteId] = useState(() => getStandaloneSiteId())
  // Focus mode: warp directly to site (from ?focus=)
  const [focusSiteId] = useState(() => getFocusSiteId())
  const [initialNav] = useState(() => getInitialCoords())
  const initialCoordsHandledRef = useRef(false)
  const focusHandledRef = useRef(false)
  // Can this browser run the globe at all? Checked once, before <Globe> mounts
  // (a standalone ?site= page never mounts it).
  const [globeSupport] = useState(() => standaloneSiteId ? null : checkGlobeSupport(document.createElement('canvas')))
  // The focus site's position aims the intro; the overlay waits for its lookup.
  const [focusLocation, setFocusLocation] = useState<[number, number] | null>(null)
  const [focusResolved, setFocusResolved] = useState(focusSiteId === null)
  // A start failure replaces the page with GlobeErrorScreen
  const [globeFailure, setGlobeFailure] = useState<{ phase: string; message: string } | null>(null)
  const globeFailureTrackedRef = useRef(false)
  // At most one ending event per load (globe_gate, globe_unsupported, globe_error, globe_abandon)
  const [endingLatch] = useState(createGlobeEndingLatch)
  // Critical items of the start that are in; the watchdog and globe_abandon's phase read them
  const startItemsRef = useRef(new Set<StartItem>())
  const watchdogRef = useRef<StallWatchdog | null>(null)
  const [loadStalled, setLoadStalled] = useState(false)
  // globe_ready has fired (useGlobeReady): later failures are 'live', not start failures
  const globeReadyRef = useRef(false)
  // Globe's loader bridge asks the same question (useStartErrorBridge)
  const isGlobeReady = useCallback(() => globeReadyRef.current, [])

  const [sites, setSites] = useState<SiteData[]>([])
  const sitesRef = useRef<SiteData[]>([])
  sitesRef.current = sites
  // The globe starts on the slim site payload; search waits for the detail fields
  const [detailsStatus, setDetailsStatus] = useState<'loading' | 'ready' | 'failed'>('loading')
  const [filteredSites, setFilteredSites] = useState<SiteData[]>([])
  const [_categories, setCategories] = useState<string[]>([])
  const [selectedCategories, setSelectedCategories] = useState<string[]>([])
  const knownCategoriesRef = useRef<Set<string>>(new Set()) // Track all categories ever seen
  const [countries, setCountries] = useState<string[]>([])
  const [selectedCountries, setSelectedCountries] = useState<string[]>([])
  const knownCountriesRef = useRef<Set<string>>(new Set()) // Track all countries ever seen
  const [selectedSources, setSelectedSources] = useState<string[]>(['ancient_nerds'])
  const [searchAllSources, setSearchAllSources] = useState(false)
  const [applyFiltersToSearch, setApplyFiltersToSearch] = useState(true)
  const [searchWithinProximity, setSearchWithinProximity] = useState(false)
  const [filterMode, setFilterMode] = useState<FilterMode>('age')
  const [ageRange, setAgeRange] = useState<[number, number]>([-5000, 1500])
  const [isLoading, setIsLoading] = useState(true) // Wait for default source before showing globe
  const [layersReady, setLayersReady] = useState(false) // Wait for coastlines/borders to load
  const [overlayFading, setOverlayFading] = useState(false) // Controls fade-out animation
  const [overlayRendered, setOverlayRendered] = useState(true) // Controls DOM presence after fade
  const [webglLost, setWebglLost] = useState(false) // GPU context died - the globe is frozen until reload
  const [loadingStatus, setLoadingStatus] = useState('Initializing...') // Dynamic loading message
  const [loadingProgress, setLoadingProgress] = useState(5) // 0-100 for progress bar
  const [downloadSpeed, setDownloadSpeed] = useState<string>('') // Download speed display
  const [downloadedMB, setDownloadedMB] = useState<number>(0) // Total MB downloaded
  const loadingStatusTimeoutRef = useRef<number | null>(null)
  const lastStatusChangeRef = useRef<number>(Date.now())
  const speedTrackingRef = useRef({
    totalBytes: 0,
    lastTotalBytes: 0,
    lastUpdateTime: Date.now(),
    smoothedSpeed: 0, // Exponential moving average
    lastActivityTime: Date.now(),
  })
  const speedIntervalRef = useRef<number | null>(null)
  // globe_idle: armed at globe_ready, disarmed by the first
  // site popup, search input or source toggle. Fires once after 30 s.
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const markGlobeActivity = useCallback(() => {
    if (idleTimerRef.current) {
      clearTimeout(idleTimerRef.current)
      idleTimerRef.current = null
    }
  }, [])


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

    // Update display every 500ms with smoothing (display only; a faster tick
    // re-rendered App and the whole Globe ten times a second during loading)
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
    }, 500)

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
    isMinimized: boolean
  }
  const [openPopups, setOpenPopups] = useState<Map<string, OpenPopup>>(new Map())

  // Empire popup support: track all open empire popups by empire ID
  interface OpenEmpirePopup {
    empire: EmpirePopupData
    yearOptions: number[]
    currentYear: number
    defaultYear?: number
    isMinimized: boolean
  }
  const [openEmpirePopups, setOpenEmpirePopups] = useState<Map<string, OpenEmpirePopup>>(new Map())

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
  // External empire year request (to sync popup period changes to globe)
  const [externalEmpireYearRequest, setExternalEmpireYearRequest] = useState<{ empireId: string; year: number } | null>(null)

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

  // Random mode state - when true, only the random site dot is shown
  const [randomModeActive, setRandomModeActive] = useState(false)

  // Contribute modal state
  const [showContributeModal, setShowContributeModal] = useState(false)
  const [isContributeMapPickerActive, setIsContributeMapPickerActive] = useState(false)
  const [contributeHoverCoords, setContributeHoverCoords] = useState<[number, number] | null>(null) // [lng, lat] - live hover
  const [wasMapPickerCancelled, setWasMapPickerCancelled] = useState(false)

  // Disclaimer modal state
  const [showDisclaimerModal, setShowDisclaimerModal] = useState(false)

  // Lyra chat modal state
  const [showLyraChat, setShowLyraChat] = useState(false)
  const [lyraChatContext, setLyraChatContext] = useState<{ type: 'global' | 'site' | 'empire'; id?: string; year?: number }>({ type: 'global' })

  // Download manager modal state
  const [showDownloadManager, setShowDownloadManager] = useState(false)
  const [showNewsFeed, setShowNewsFeed] = useState(false)
  const [demoMode, setDemoMode] = useState(false)

  // Toggle body class when news feed is open so right-side UI shifts left
  useEffect(() => {
    document.body.classList.toggle('news-feed-open', showNewsFeed)
    return () => { document.body.classList.remove('news-feed-open') }
  }, [showNewsFeed])

  // Demo API for Puppeteer-driven video recording (?demo=1)
  useEffect(() => {
    if (!isDemoMode()) return
    registerAppDemoApi({ setFilterMode, setAgeRange, setFlyToCoords, setDemoMode, setSelectedSources, handleLoadSources, openSitePopup, closeAllPopups, sitesRef })
  }, [])

  // Toggle body class for demo mode (hides all UI except the globe)
  useEffect(() => {
    document.body.classList.toggle('demo-mode', demoMode)
    return () => { document.body.classList.remove('demo-mode') }
  }, [demoMode])

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

  // Lyra chat handlers
  const handleAIAgentClick = useCallback(() => {
    setLyraChatContext({ type: 'global' })
    setShowLyraChat(true)
  }, [])

  const handleLyraHighlightSites = useCallback((siteIds: string[]) => {
    setListFrozenSiteIds(siteIds)
  }, [])

  // Opens popup for a site
  const openSitePopup = useCallback((siteData: SiteData) => {
    markGlobeActivity()
    setOpenPopups(prev => {
      const next = new Map(prev)
      if (!next.has(siteData.id)) {
        next.set(siteData.id, {
          site: siteData,
          isMinimized: false,
        })
      }
      return next
    })
    setIsLoadingDetail(false)
  }, [markGlobeActivity])

  // Fetch site details and open popup
  const handleSiteClick = useCallback(async (site: SiteData | null) => {
    if (!site) return

    // If popup already open for this site, don't open another
    if (openPopups.has(site.id)) return

    setIsLoadingDetail(true)

    let siteData: SiteData | null = null
    try {
      // Fetch full site details (fast API call)
      const response = await offlineFetch(`${config.api.baseUrl}/sites/${site.id}`)

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
    } catch (error) {
      console.warn('Could not fetch site data:', error)
    }

    // Without the detail answer the popup opens from the bulk data, once that
    // carries its detail fields (the globe payload has no description or image)
    try {
      openSitePopup(siteData ?? await withSiteDetails(site))
    } catch (error) {
      console.error('Could not open the site: its details failed to load', error)
      setIsLoadingDetail(false)
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

  // Close all popups (used by demo API)
  const closeAllPopups = useCallback(() => {
    setOpenPopups(new Map())
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

  // ========== Empire Popup Functions ==========

  // Open empire popup - takes empire ID and looks up config
  const openEmpirePopup = useCallback((empireId: string, defaultYear?: number, realYearOptions?: number[]) => {
    // Don't open if already open
    if (openEmpirePopups.has(empireId)) return

    // Find empire config
    const empireConfig = EMPIRES.find(e => e.id === empireId)
    if (!empireConfig) {
      console.warn('Empire not found:', empireId)
      return
    }

    // Use real year options from Globe metadata (always available when empire is loaded)
    const yearOptions = realYearOptions && realYearOptions.length > 0
      ? realYearOptions
      : []
    const currentYear = empireSliderYears[empireId] ?? defaultYear ?? yearOptions[0] ?? 0

    // Create empire popup data
    const empireData: EmpirePopupData = {
      id: empireConfig.id,
      name: empireConfig.name,
      region: empireConfig.region,
      color: empireConfig.color,
    }

    setOpenEmpirePopups(prev => {
      const next = new Map(prev)
      next.set(empireId, {
        empire: empireData,
        yearOptions,
        currentYear,
        defaultYear,
        isMinimized: false
      })
      return next
    })
  }, [openEmpirePopups, empireSliderYears])

  // Close empire popup
  const closeEmpirePopup = useCallback((empireId: string) => {
    setOpenEmpirePopups(prev => {
      const next = new Map(prev)
      next.delete(empireId)
      return next
    })
  }, [])

  // Update empire popup year - tells globe to update, which syncs back via onEmpireYearsChange
  const setEmpirePopupYear = useCallback((empireId: string, year: number) => {
    // Tell the globe to update its borders for this year
    // Globe will find closest available year and sync back via onEmpireYearsChange
    // which updates empireSliderYears - this keeps slider in sync with actual data
    setExternalEmpireYearRequest({ empireId, year })
  }, [])

  // Update minimized state for empire popup
  const setEmpirePopupMinimized = useCallback((empireId: string, isMinimized: boolean) => {
    setOpenEmpirePopups(prev => {
      const next = new Map(prev)
      const popup = next.get(empireId)
      if (popup) {
        next.set(empireId, { ...popup, isMinimized })
      }
      return next
    })
  }, [])

  // Detail fields (description, card, image, links) the globe payload leaves out.
  // Merged into the sites already on screen; search waits for them. A failure is
  // shown in the search header and rethrown to the caller, which reports it.
  const loadDetails = useCallback(async (): Promise<void> => {
    try {
      const byId = await loadSiteDetails()
      setSites(prev => mergeSiteDetails(prev, byId))
      setDetailsStatus('ready')
    } catch (err) {
      setDetailsStatus('failed')
      throw err
    }
  }, [])

  // App's part of the globe's background queue, after the intro: the site details
  // first, the service worker (and the removal of caches earlier workers left) last.
  // Only production builds have a /sw.js (the PWA plugin serves none in dev), so dev
  // registers none, as before.
  const appBackgroundTasks = useMemo((): AppBackgroundTasks => ({
    details: () => loadDetails(),
    sw: import.meta.env.PROD ? () => serviceWorkerTask() : null,
  }), [loadDetails])

  /** The globe cannot start (or broke after it had: phase 'live'): error screen, one globe_error. */
  const failGlobe = useCallback((phase: string, err: unknown) => {
    const message = errorProps(err instanceof Error ? err.message : err).message
    console.error(`[globe] failed (${phase})`, err)
    watchdogRef.current?.stop()
    setGlobeFailure(prev => prev ?? { phase, message })
    if (globeFailureTrackedRef.current) return
    globeFailureTrackedRef.current = true
    // A live failure follows globe_ready, which closed the latch. A start failure is this
    // load's ending, sent when its screen shows (useGlobeScreenEnding, below): not behind
    // the phone gate, where a gate link used first is the ending instead.
    if (phase === LIVE_PHASE) track('globe_error', { phase, message })
  }, [])

  const handleGlobeError = useCallback((err: unknown) => {
    failGlobe(failurePhase(err, globeReadyRef.current), err instanceof GlobeStartError ? err.cause : err)
  }, [failGlobe])

  /** A critical item of the start is in: the watchdog waits again. */
  const markStartProgress = useCallback((item: StartItem) => {
    startItemsRef.current.add(item)
    watchdogRef.current?.progress()
    setLoadStalled(false)
  }, [])

  // A layout effect, so the requests go out before the Globe's passive effects
  // (scene, WebGL context, geometry) run in the same commit.
  useLayoutEffect(() => {
    // Standalone mode: fetch only the single site, skip everything else
    if (standaloneSiteId) {
      const loadStandaloneSite = async () => {
        try {
          // Initialize DataStore to load source metadata (needed for display names)
          // This loads sources.json which populates getSourceInfo()
          await fetchSites('globe')

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
          openSitePopup(siteData)
          setIsLoading(false)
        } catch (error) {
          console.error('Failed to load site:', error)
          setIsLoading(false)
        }
      }
      loadStandaloneSite()
      return
    }

    // A browser that cannot show the globe downloads nothing and asks no third party
    if (globeSupport && !globeSupport.ok) return

    let cancelled = false
    const lookups = new AbortController()

    // IP geolocation aims the intro; it runs in parallel and the start never waits
    // for it (utils/ipLocation.ts: a deadline per provider). A result that arrives
    // after the warp has started is ignored by Globe. ?lat&lon always wins.
    if (!initialNav) {
      lookupIpLocation(lookups.signal).then(
        location => { if (location) setUserLocation(location) },
        (reason: unknown) => { if (!lookups.signal.aborted) throw reason }, // rejects only when aborted
      )
    }

    // Focus mode: the warp lands on the site. The overlay waits for this lookup
    // (focusResolved), at most its deadline (utils/focusLocation.ts); when it
    // fails the intro aims at the IP location, as always.
    if (focusSiteId) {
      lookupFocusLocation(focusSiteId, lookups.signal).then(
        location => {
          if (location) setFocusLocation(location)
          setFocusResolved(true)
        },
        (reason: unknown) => { if (!lookups.signal.aborted) throw reason }, // rejects only when aborted
      )
    }

    // Normal mode: the default source first, then the globe shows its dots
    const loadData = async () => {
      updateLoadingStatus('Loading archaeological sites...')
      setLoadingProgress(p => Math.max(p, 20))
      let data: SiteData[]
      try {
        data = await fetchSites(globeSiteFields(focusSiteId))
      } catch (error) {
        setDataSourceError()  // Set error state for red LED indicator
        throw error
      }
      if (cancelled) return
      setSites(data)
      // A focus load (full payload) and offline mode start with their details
      if (DataStore.detailsReady) setDetailsStatus('ready')

      // Get source metadata from DataStore (already loaded in parallel with sites)
      const sources = DataStore.getSources()
      const sourcesMetaMap: Record<string, SourceMeta> = {}
      for (const source of sources) {
        sourcesMetaMap[source.id] = {
          n: source.name,
          c: source.color,
          cnt: source.recordCount,
          pri: source.isPrimary,
          p: source.priority ?? 999,
          on: source.enabledByDefault,
          cat: source.category,
        }
      }
      setSourcesMeta(sourcesMetaMap)

      // Get all source IDs from DataStore
      const allSourceIds = DataStore.getSources().map(s => s.id)

      updateLoadingStatus('Preparing globe view...')
      setLoadingProgress(p => Math.max(p, 50))

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
      // Monotonic: the layers may have finished first (the bar is at 90 then)
      setLoadingProgress(p => Math.max(p, 65))
      markStartProgress('sites')
      // Note: Additional sources are NOT loaded automatically - user must click "Load Sources" button
      // The detail fields follow in the globe's background queue (appBackgroundTasks.details)
    }
    // The globe cannot start without its sites: the error screen, not an empty globe
    loadData().catch((err: unknown) => {
      if (!cancelled) failGlobe('sites', err)
    })
    return () => {
      cancelled = true
      lookups.abort(new Error('app unmounted'))
    }
  }, [standaloneSiteId, openSitePopup, globeSupport, initialNav, focusSiteId, updateLoadingStatus, markStartProgress, failGlobe])

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

    // Include ALL sources from metadata — no filtering, fully data-driven
    for (const [sourceId, meta] of Object.entries(sourcesMeta)) {
      result.push({
        id: sourceId,
        name: meta?.n || sourceId.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
        color: meta?.c || SOURCE_COLORS[sourceId] || SOURCE_COLORS.default || '#9ca3af',
        count: meta.cnt,
        primary: meta.pri,
        priority: meta.p ?? 999,
        category: meta.cat,
      })
    }

    // Sort by priority (from DB), then by count descending
    return result.sort((a, b) => {
      if (a.priority !== b.priority) return a.priority - b.priority
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

  // Shared search hook — encapsulates debouncing, API search, and client-side filtering
  const siteSearch = useSiteSearch({
    sites,
    sourceNameMap,
    selectedSources,
    selectedCategories,
    allCategories: categoriesFromActiveSources,
    selectedCountries,
    allCountries: countries,
    ageRange,
    searchAllSources,
    applyFiltersToSearch,
    detailsReady: detailsStatus === 'ready',
    spatialFilter: searchWithinProximity && proximityCenter
      ? { center: proximityCenter, radius: proximityRadius }
      : null,
    empireFilter: searchWithinEmpires && visibleEmpireIds.size > 0
      ? { visibleEmpireIds, empireSliderYears, empirePolygons }
      : null,
  })
  const { searchResults, apiSearchResults, searchQuery, setSearchQuery, debouncedQuery: debouncedSearchQuery, isSearching } = siteSearch

  // Typing in the filter panel's search box or toggling a source counts as
  // globe activity (disarms globe_idle); programmatic setSearchQuery calls
  // (focus deep link, random site) do not.
  const handleFilterSearchChange = useCallback((q: string) => {
    markGlobeActivity()
    setSearchQuery(q)
  }, [markGlobeActivity, setSearchQuery])
  const handleSourceChange = useCallback((ids: string[]) => {
    markGlobeActivity()
    setSelectedSources(ids)
  }, [markGlobeActivity])

  // Handle search result selection (wraps hook helper with globe-specific fly-to)
  const handleSearchResultSelect = useCallback(async (siteId: string, openPopup: boolean) => {
    // Find site before opening popup — if it came from API search, add it to sites so globe shows the dot
    const apiSite = apiSearchResults.find(s => s.id === siteId)
    if (apiSite) {
      setSites(prev => prev.some(s => s.id === siteId) ? prev : [...prev, apiSite])
    }

    await siteSearch.handleSearchResultSelect(siteId, openPopup, (site) => {
      handleSiteClick(site)
    })
    // Fly to the site regardless of popup
    const site = sites.find(s => s.id === siteId) || apiSearchResults.find(s => s.id === siteId)
    if (site) {
      setFlyToCoords(null)
      setTimeout(() => setFlyToCoords(site.coordinates), 10)
    }
  }, [siteSearch, sites, apiSearchResults, handleSiteClick])

  // Focus mode (first load): warp lands on the site, fill search bar and select dot
  useEffect(() => {
    if (!focusSiteId || focusHandledRef.current || sites.length === 0) return
    focusHandledRef.current = true

    const site = sites.find(s => s.id === focusSiteId)
    if (!site) return

    track('globe_focus', { site: site.id, country: site.location })
    setSearchQuery(site.title)
    setListFrozenSiteIds([site.id])
  }, [focusSiteId, sites, setSearchQuery])

  // Coordinate fly-to from URL params (?lat=&lon=&proximity=1)
  useEffect(() => {
    if (!initialNav || initialCoordsHandledRef.current) return
    initialCoordsHandledRef.current = true
    setFlyToCoords(null)
    requestAnimationFrame(() => setFlyToCoords(initialNav.coords))
    if (initialNav.proximity) {
      setProximityCenter(initialNav.coords)
      setSearchWithinProximity(true)
    }
  }, [initialNav])

  // Listen for postMessage from search page / Lyra — switch site or fly to coords
  useEffect(() => {
    const handler = async (e: MessageEvent) => {
      if (e.origin !== window.location.origin) return
      // Handle fly-to-coords from Lyra coordinate links
      if (e.data?.type === 'fly-to-coords' && e.data?.lat != null && e.data?.lon != null) {
        setFlyToCoords(null)
        requestAnimationFrame(() => setFlyToCoords([e.data.lon, e.data.lat]))
        // Activate proximity search around these coordinates
        if (e.data.activateProximity) {
          setProximityCenter([e.data.lon, e.data.lat])
          setSearchWithinProximity(true)
        }
        return
      }
      if (e.data?.type !== 'focus-site' || !e.data?.siteId) return

      const siteId = e.data.siteId as string
      let site = sites.find(s => s.id === siteId)
      if (!site) {
        try {
          const res = await fetch(`${config.api.baseUrl}/sites/${siteId}`)
          if (res.ok) {
            const detail = await res.json()
            site = apiDetailToSiteData(detail)
          }
        } catch { /* ignore */ }
      }
      if (!site) return

      setSearchQuery(site.title)
      setListFrozenSiteIds([site.id])
      setFlyToCoords(null)
      requestAnimationFrame(() => setFlyToCoords(site!.coordinates))
    }
    window.addEventListener('message', handler)
    return () => window.removeEventListener('message', handler)
  }, [sites, setSearchQuery])

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
    reportAchievementEvent('random_site_used')

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

  // Reset all filters to defaults (uses enabledByDefault from source metadata)
  const handleResetAllFilters = useCallback(() => {
    const defaultIds = Object.entries(sourcesMeta)
      .filter(([, meta]) => meta.on)
      .map(([id]) => id)
    // Fallback to first primary source if none are enabledByDefault
    const resetIds = defaultIds.length > 0
      ? defaultIds
      : Object.entries(sourcesMeta).filter(([, m]) => m.pri).map(([id]) => id)
    setSelectedSources(resetIds)
    setAgeRange(DEFAULT_AGE_RANGE)
    const defaultSourceSites = sites.filter(s => resetIds.includes(s.sourceId))
    const defaultCategories = [...new Set(defaultSourceSites.map(s => s.category).filter(Boolean))].sort()
    const defaultCountries = [...new Set(defaultSourceSites.map(s => extractCountry(s.location)).filter(c => c !== 'Unknown'))].sort()
    setSelectedCategories(defaultCategories)
    setSelectedCountries(defaultCountries)
  }, [sites, sourcesMeta])

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
    reportAchievementEvent('proximity_used')
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

  // Handle empire year changes from Globe - also sync to any open popups
  const handleEmpireYearsChange = useCallback((years: Record<string, number>) => {
    // Merge incoming years with existing to preserve any directly-set values
    setEmpireSliderYears(prev => ({ ...prev, ...years }))
    // Sync year to any open empire popups
    setOpenEmpirePopups(prev => {
      let changed = false
      const next = new Map(prev)
      for (const [empireId, popup] of next) {
        const newYear = years[empireId]
        if (newYear !== undefined && newYear !== popup.currentYear) {
          next.set(empireId, { ...popup, currentYear: newYear })
          changed = true
        }
      }
      return changed ? next : prev
    })
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

    const [centerLng, centerLat] = proximityCenter

    return sitesWithProximity
      .filter(site => site.isInsideProximity)
      .sort((a, b) => {
        const [aLng, aLat] = a.coordinates
        const [bLng, bLat] = b.coordinates
        const distA = haversineDistance(centerLat, centerLng, aLat, aLng)
        const distB = haversineDistance(centerLat, centerLng, bLat, bLng)
        return distA - distB
      })
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
    // A query needs the detail fields (it matches descriptions): until they are in,
    // the dots keep their previous filter instead of a match on half the data
    if (isSearching && detailsStatus !== 'ready') return

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
        (site.altNames && site.altNames.some(an => normalizeForSearch(an).includes(query))) ||
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
  }, [sites, detailsStatus, selectedSources, selectedCategories, categoriesFromActiveSources, selectedCountries, countriesFromActiveSources, debouncedSearchQuery, searchAllSources, ageRange, applyFiltersToSearch, searchWithinProximity, proximityCenter, proximityRadius, searchWithinEmpires, visibleEmpireIds, empireSliderYears, empirePolygons, listFrozenSiteIds])

  // Crawl progress bar from 65→90% while globe layers are loading (unknown duration)
  useEffect(() => {
    if (isLoading || layersReady) return
    const interval = setInterval(() => {
      setLoadingProgress(p => Math.min(p + 1, 90))
    }, 400)
    return () => clearInterval(interval)
  }, [isLoading, layersReady])

  const gateShowing = isMobile && !mobileWarningDismissed
  const gateShowingRef = useRef(gateShowing)
  gateShowingRef.current = gateShowing

  // The overlay fades as soon as the sites, the critical layers and (focus mode)
  // the focus site's position are in; the warp starts with the fade. Never behind
  // the phone gate, which unmounts the overlay and the Globe (useGlobeBehindGate).
  const loadingComplete = !gateShowing && !isLoading && layersReady && focusResolved
  // The bar's 100 %, the READY stamp and ALL SYSTEMS NOMINAL mean this moment too
  useEffect(() => {
    if (loadingComplete) setLoadingProgress(100)
  }, [loadingComplete])
  useEffect(() => {
    if (loadingComplete && overlayRendered && !overlayFading) setOverlayFading(true)
  }, [loadingComplete, overlayRendered, overlayFading])
  useGlobeBehindGate(gateShowing, overlayFading, {
    resetLayers: () => setLayersReady(false),
    removeOverlay: () => setOverlayRendered(false),
  })

  // globe_ready when the visitor sees the globe: the overlay fades on loadingComplete,
  // with no error screen over it and a live WebGL context under it
  const armGlobeIdle = useCallback(() => {
    idleTimerRef.current = setTimeout(() => track('globe_idle', { ms: 30000 }), 30000)
  }, [])
  useGlobeReady(loadingComplete && !globeFailure && !webglLost, endingLatch, globeReadyRef, armGlobeIdle)

  const handleGateChoice = useCallback((choice: GateChoice) => {
    reportGateChoice(choice, endingLatch)
    if (choice === 'globe') setMobileWarningDismissed(true)
  }, [endingLatch])

  // globe_abandon: armed from mount (the gate phase included), until this load ends
  useEffect(() => {
    if (standaloneSiteId) return
    return installGlobeAbandon({
      latch: endingLatch,
      getPhase: () => loadPhase(gateShowingRef.current, startItemsRef.current),
      now: () => performance.now(),
    })
  }, [standaloneSiteId, endingLatch])

  // globe_unsupported or a start failure's globe_error, once, when its screen actually
  // shows: after the phone gate (App renders the gate first)
  const screenEnding = useMemo((): ScreenEnding | null => {
    if (globeSupport && !globeSupport.ok) {
      return { name: 'globe_unsupported', props: { reason: globeSupport.reason, detail: globeSupport.detail } }
    }
    if (globeFailure && globeFailure.phase !== LIVE_PHASE) {
      return { name: 'globe_error', props: { phase: globeFailure.phase, message: globeFailure.message } }
    }
    return null
  }, [globeSupport, globeFailure])
  useGlobeScreenEnding(endingLatch, screenEnding, gateShowing)

  // Loading watchdog: while the globe starts, 20 s of visible time without any
  // critical item progressing offers a reload in the hint box. Loading goes on.
  const startWatched = !standaloneSiteId && !gateShowing && globeSupport?.ok === true
    && !globeFailure && !loadingComplete && !webglLost
  useEffect(() => {
    if (!startWatched) return
    const dog = createStallWatchdog({
      timeoutMs: START_STALL_MS,
      onStall: () => setLoadStalled(true),
      paused: document.visibilityState === 'hidden',
    })
    watchdogRef.current = dog
    const onVisibility = () => (document.visibilityState === 'hidden' ? dog.pause() : dog.resume())
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      dog.stop()
      watchdogRef.current = null
      setLoadStalled(false)
    }
  }, [startWatched])

  // The critical layers are in. The load is not ready yet: the overlay may still wait
  // for the sites or the focus lookup (globe_ready: useGlobeReady, above), so the bar
  // stops short of 100 % and the status keeps naming the step still pending
  const handleLayersReady = useCallback(() => {
    setLoadingProgress(p => Math.max(p, 90))
    setLayersReady(true)
  }, [])

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
            <a href="/globe.html" className="standalone-back-btn">Back to Map</a>
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
            window.location.href = '/globe.html'
          }}
          isStandalone={true}
        />
      </div>
    )
  }

  // Mobile users see desktop-only message (unless dismissed)
  if (gateShowing) return <PhoneGate onChoice={handleGateChoice} />

  // A browser that cannot run the globe, and a globe that failed: a clear screen, never a black one
  if (globeSupport && !globeSupport.ok) return <GlobeUnsupported reason={globeSupport.reason} detail={globeSupport.detail} />
  if (globeFailure) return <GlobeErrorScreen phase={globeFailure.phase} message={globeFailure.message} />

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
            <img src={BRAND_ASSETS.logo} alt="Ancient Nerds" className="loading-logo" />
          </div>
          <div className="loading-info-bar">
            <div className="loading-info-inner" />
            <div className="loading-ct" /><div className="loading-ctr" />
            <div className="loading-cbl" /><div className="loading-cbr" />
            <div className="loading-bar-header">
              <span className="loading-bar-stamp">{webglLost ? 'GPU LOST' : loadingComplete ? 'READY' : 'LOADING'}</span>
              {downloadedMB > 0.1 && <span className="loading-bar-counter">{downloadedMB.toFixed(1)} MB</span>}
              {downloadSpeed && <span className="loading-bar-speed">{downloadSpeed}</span>}
            </div>
            <div className="loading-bar-track">
              <div className="loading-bar-fill" style={{ width: `${loadingProgress}%` }} />
            </div>
            <div className="loading-bar-leds">
              {[1,2,3,4,5,6,7].map(i => (
                <div key={i} className={`loading-bar-led led-${i}`} />
              ))}
            </div>
            <div className="loading-text">{webglLost ? 'GRAPHICS CONTEXT LOST' : loadingComplete ? 'ALL SYSTEMS NOMINAL' : loadingStatus.toUpperCase()}</div>
            {/* The button takes the hint's place rather than joining it: the bar
                keeps its height, and the visitor gets the one action left. */}
            {webglLost ? (
              <button className="loading-retry" onClick={() => window.location.reload()}>Reload the globe</button>
            ) : loadStalled ? (
              <button className="loading-retry" onClick={() => window.location.reload()}>Taking unusually long — reload</button>
            ) : (
              <div className="loading-hint">For best performance, enable hardware acceleration in your browser</div>
            )}
          </div>
        </div>
      )}
      {/* Once the overlay is gone the globe is the page, so the loss needs its
          own notice - a frozen globe with no explanation is what the one real
          visitor sat through on 2026-09-18. */}
      {!overlayRendered && webglLost && (
        <div className="webgl-lost-bar" role="alert">
          <span>The 3D globe lost its graphics context and stopped.</span>
          <button className="webgl-lost-btn" onClick={() => window.location.reload()}>Reload the globe</button>
        </div>
      )}
      {/* Loading cursor overlay for site detail loading */}
      {isLoadingDetail && (
        <div className="loading-cursor-overlay">
          <div className="loading-cursor-spinner" />
        </div>
      )}
      <GlobeErrorBoundary onError={handleGlobeError}><Globe
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
        initialPosition={initialNav?.coords ?? focusLocation ?? userLocation}
        onLayersReady={handleLayersReady}
        isGlobeReady={isGlobeReady}
        onStartProgress={markStartProgress}
        appBackgroundTasks={appBackgroundTasks}
        onWebglLost={(reason) => {
          setWebglLost(true)
          // Before globe_ready this is the load's ending (through the latch), after it a live loss
          reportWebglLost(endingLatch, reason, globeReadyRef.current)
        }}
        onWebglRestored={() => setWebglLost(false)}
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
        externalEmpireYearRequest={externalEmpireYearRequest}
        onExternalEmpireYearRequestHandled={() => setExternalEmpireYearRequest(null)}
        onEmpireClick={openEmpirePopup}
        onOfflineClick={() => setShowDownloadManager(true)}
        isOffline={isOffline}
        onNewsFeedClick={() => setShowNewsFeed(prev => !prev)}
        isNewsFeedOpen={showNewsFeed}
      /></GlobeErrorBoundary>
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
        isSearching={isSearching}
        searchError={detailsStatus === 'failed' ? 'Search unavailable: site details failed to load. Reload the page.' : null}
        filterMode={filterMode}
        ageRange={ageRange}
        onCategoryChange={handleCategoryChange}
        onCountryChange={handleCountryChange}
        onSourceChange={handleSourceChange}
        onSearchChange={handleFilterSearchChange}
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
            onSiteUpdate={(id, updated) => {
              // Update sites array so globe dots use fresh data
              setSites(prev => prev.map(s => s.id === id ? updated : s))
              // Update the popup's stored site so close/reopen keeps the change
              setOpenPopups(prev => {
                const next = new Map(prev)
                const existing = next.get(id)
                if (existing) next.set(id, { ...existing, site: updated })
                return next
              })
            }}
            onAskLyra={(ctxType, ctxId, ctxYear) => {
              setLyraChatContext({ type: ctxType, id: ctxId, year: ctxYear })
              setShowLyraChat(true)
            }}
          />
        )
      })}
      {/* Render all open empire popups */}
      {Array.from(openEmpirePopups.entries()).map(([empireId, popup]) => {
        // Calculate stack index for minimized empire popups (after site popups)
        const minimizedSitePopups = Array.from(openPopups.values()).filter(p => p.isMinimized)
        const minimizedEmpirePopups = Array.from(openEmpirePopups.values()).filter(p => p.isMinimized)
        const minimizedIndex = minimizedEmpirePopups.findIndex(p => p.empire.id === empireId)
        // Stack empire popups after site popups
        const stackIndex = minimizedIndex >= 0 ? minimizedSitePopups.length + minimizedIndex : -1

        return (
          <SitePopup
            key={`empire-${empireId}`}
            empire={popup.empire}
            empireYear={empireSliderYears[empireId] ?? popup.currentYear}
            empireYearOptions={popup.yearOptions}
            empireDefaultYear={popup.defaultYear}
            onEmpireYearChange={(year) => setEmpirePopupYear(empireId, year)}
            onClose={() => closeEmpirePopup(empireId)}
            onMinimizedChange={(isMin) => setEmpirePopupMinimized(empireId, isMin)}
            minimizedStackIndex={stackIndex}
            onAskLyra={(ctxType, ctxId, ctxYear) => {
              setLyraChatContext({ type: ctxType, id: ctxId, year: ctxYear })
              setShowLyraChat(true)
            }}
          />
        )
      })}

      {/* News Feed Panel - slides in from right */}
      <LazyErrorBoundary><Suspense fallback={null}>
        {showNewsFeed && (
          <NewsFeedPanel
            onClose={() => setShowNewsFeed(false)}
            onSiteHover={setHighlightedSiteId}
            onSiteClick={(siteName, lat, lon) => {
              setSearchQuery(siteName)
              setFlyToCoords(null)
              setTimeout(() => setFlyToCoords([lon, lat]), 10)
              const query = normalizeForSearch(siteName)
              const match = sites.find(s =>
                selectedSources.includes(s.sourceId) &&
                normalizeForSearch(s.title).includes(query)
              ) || sites.find(s => normalizeForSearch(s.title).includes(query))
              if (match) {
                updateSelection([match.id])
              }
            }}
          />
        )}
      </Suspense></LazyErrorBoundary>

      {/* Lazy-loaded modals wrapped in Suspense for faster initial load */}
      <LazyErrorBoundary resetKey={showContributeModal}><Suspense fallback={null}>
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
          ensureOfflineWorker={import.meta.env.PROD ? ensureServiceWorkerActive : null}
        />

        {/* Lyra Chat Modal */}
        <LyraChatModal
          isOpen={showLyraChat}
          onClose={() => setShowLyraChat(false)}
          contextType={lyraChatContext.type}
          contextId={lyraChatContext.id}
          contextYear={lyraChatContext.year}
          onHighlightSites={handleLyraHighlightSites}
          onFlyToSite={(coords) => {
            setFlyToCoords(null)
            setTimeout(() => setFlyToCoords(coords), 10)
          }}
          onOpenSitePopup={openSitePopup}
          onOpenEmpirePopup={openEmpirePopup}
        />
      </Suspense></LazyErrorBoundary>
    </>
  )
}

/**
 * App wrapper that provides offline context to all components
 */
function App() {
  return (
    <AuthProvider>
      <OfflineProvider>
        <AppContent />
        <AchievementToast />
      </OfflineProvider>
    </AuthProvider>
  )
}

export default App
