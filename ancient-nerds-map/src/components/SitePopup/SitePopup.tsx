import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { SiteData, PERIOD_COLORS, getSourceColor, getCategoryColor, getSourceInfo } from '../../data/sites'
import { config } from '../../config'
import { useOffline } from '../../contexts/OfflineContext'
import { reportAchievementEvent } from '../../utils/cardApi'

// Unified content service for gallery items
import { toLightboxImages } from '../../services/connectors'

// Wikipedia summary type and fetcher (inline to avoid dependency on old service)
interface WikipediaSummary {
  extract: string
  url: string
  thumbnail?: string
}

async function getEmpireWikipediaSummary(empireName: string): Promise<WikipediaSummary | null> {
  try {
    const normalizedTitle = empireName.replace(/ /g, '_')
    const response = await fetch(
      `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(normalizedTitle)}`,
      { headers: { 'Accept': 'application/json' } }
    )
    if (!response.ok) {
      // Try with "Empire" suffix
      if (!empireName.toLowerCase().includes('empire')) {
        const fallbackResponse = await fetch(
          `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(empireName + '_Empire')}`,
          { headers: { 'Accept': 'application/json' } }
        )
        if (fallbackResponse.ok) {
          const data = await fallbackResponse.json()
          if (data.extract) {
            return {
              extract: data.extract,
              thumbnail: data.thumbnail?.source,
              url: data.content_urls?.desktop?.page || `https://en.wikipedia.org/wiki/${empireName}_Empire`
            }
          }
        }
      }
      return null
    }
    const data = await response.json()
    if (!data.extract || data.type === 'disambiguation') return null
    return {
      extract: data.extract,
      thumbnail: data.thumbnail?.source,
      url: data.content_urls?.desktop?.page || `https://en.wikipedia.org/wiki/${normalizedTitle}`
    }
  } catch {
    return null
  }
}

// Seshat data service
import { getSeshatDataForEmpire, getWikipediaUrl, getSeshatPolityName } from '../../services/seshatService'
import { getAvailablePeriodsForEmpire, getSeshatPolityIdForYear } from '../../config/seshatMapping'
import type { SeshatPolityData } from '../../types/seshat'

// Components
import ImageLightbox, { LightboxImage } from '../ImageLightbox'
import ModelViewer from '../ModelViewer'

// Extracted components
import { usePopupWindow, WindowControls, ResizeHandles, MinimizedBar } from './window'
import { useGalleryData, useEmpireGalleryData, GalleryTabs, GalleryContent, ConnectorStatus } from './gallery'
import { useAdminMode, AdminEditPanel } from './admin'
import {
  HeroHeader,
  LocationSection,
  DescriptionSection,
  MapSection,
  EmpireStatsSection,
  EmpireWarfareSection,
  EmpireSocialSection,
  EmpireEconomySection,
  EmpireCrisisSection,
  EmpireSuccessionSection
} from './sections'

// Alternate sources
import { useAlternateSources, alternateToSiteData } from './useAlternateSources'

// Types
import type { SitePopupProps, EmpireSeshatTab, AlternateSource } from './types'

export default function SitePopup({
  site,
  onClose,
  onSetProximity,
  onFlyTo,
  onHighlight,
  onSelect,
  isStandalone = false,
  onMinimizedChange,
  minimizedStackIndex = -1,
  onSiteUpdate,
  onAskLyra,
  empire,
  empireYear,
  empireYearOptions,
  empireDefaultYear,
  onEmpireYearChange
}: SitePopupProps) {
  // Auth: read directly from localStorage (no AuthProvider on the globe page)
  const authToken = useMemo(() => localStorage.getItem('an_auth_token'), [])
  const [isFounder, setIsFounder] = useState(false)
  useEffect(() => {
    if (!authToken) return
    fetch(`${config.api.baseUrl}/auth/me`, {
      headers: { 'Authorization': `Bearer ${authToken}` },
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.is_founder) setIsFounder(true) })
      .catch(() => {})
  }, [authToken])

  // Offline mode context
  const { isOffline } = useOffline()

  // Empire mode detection
  const isEmpireMode = !!empire

  // Wikipedia summary for empire description
  const [wikiSummary, setWikiSummary] = useState<WikipediaSummary | null>(null)
  const [wikiLoading, setWikiLoading] = useState(false)

  // Active Seshat tab for empire mode
  const [activeSeshatTab, setActiveSeshatTab] = useState<EmpireSeshatTab>('overview')

  // Get the current period name based on selected year
  const currentPeriodName = useMemo(() => {
    if (!empire) return null
    return getSeshatPolityName(empire.id, empireYear)
  }, [empire?.id, empireYear])

  // Display name: use period name if different from empire name, otherwise empire name
  const displayEmpireName = useMemo(() => {
    if (!empire) return ''
    // If we have a period-specific name that's different, use it
    if (currentPeriodName && currentPeriodName !== empire.name) {
      return currentPeriodName
    }
    return empire.name
  }, [empire?.name, currentPeriodName])

  // Fetch Wikipedia summary for the current period (or empire name as fallback)
  useEffect(() => {
    if (!empire || isOffline) return
    setWikiLoading(true)

    // Try period-specific name first, then fall back to empire name
    const searchName = currentPeriodName || empire.name

    getEmpireWikipediaSummary(searchName)
      .then((result) => {
        if (result) {
          setWikiSummary(result)
        } else if (currentPeriodName && currentPeriodName !== empire.name) {
          // If period name didn't work, try the base empire name
          return getEmpireWikipediaSummary(empire.name)
        }
        return null
      })
      .then((fallbackResult) => {
        if (fallbackResult) setWikiSummary(fallbackResult)
      })
      .catch(() => setWikiSummary(null))
      .finally(() => setWikiLoading(false))
  }, [empire?.name, currentPeriodName, isOffline])

  // Seshat data for empire - loaded synchronously from bundled data
  const seshatData: SeshatPolityData | null = useMemo(() => {
    if (!empire) return null
    return getSeshatDataForEmpire(empire.id, empireYear)
  }, [empire?.id, empireYear])

  // Get Wikipedia URL - prioritize the URL from the Wikipedia API that provided the description
  // This ensures the link points to the actual source of the description text
  const empireWikipediaUrl = useMemo(() => {
    if (!empire) return null
    // Use wikiSummary.url first (matches the description), fallback to Seshat data
    return wikiSummary?.url || getWikipediaUrl(empire.id, empireYear)
  }, [empire?.id, empireYear, wikiSummary?.url])

  // Truncate Wikipedia description to 3 sentences
  const truncatedDescription = useMemo(() => {
    if (!wikiSummary?.extract) return ''
    const text = wikiSummary.extract
    // Match sentences ending with . ! or ? (followed by space or end)
    const sentences = text.match(/[^.!?]*[.!?]+/g) || []
    if (sentences.length <= 3) return text
    return sentences.slice(0, 3).join('').trim()
  }, [wikiSummary?.extract])

  // Create dummy site data for empire mode
  // Use period-specific name when available for better context
  const dummySite: SiteData = useMemo(() => {
    return {
      id: empire?.id || '',
      title: displayEmpireName,
      coordinates: [0, 0],
      category: '',
      period: '',
      sourceId: 'seshat',
      location: empire?.region || '',
      description: wikiSummary?.extract || '',
      sourceUrl: empireWikipediaUrl || undefined
    }
  }, [empire, displayEmpireName, wikiSummary, empireWikipediaUrl])

  // Admin mode hook (only used for sites)
  const adminMode = useAdminMode({
    site: site || dummySite,
    onSiteUpdate,
    authToken,
  })

  // Alternate sources for source switching
  const { alternates } = useAlternateSources(site)
  const [overrideSite, setOverrideSite] = useState<SiteData | null>(null)

  // Build full source list: original site + alternates, so switching back is always possible
  const baseSite = isEmpireMode ? dummySite : adminMode.localSite
  const allSources = useMemo(() => {
    if (!alternates.length) return alternates
    const baseSourceInfo = getSourceInfo(baseSite.sourceId)
    const primary: AlternateSource = {
      id: baseSite.id,
      sourceId: baseSite.sourceId || '',
      sourceName: baseSourceInfo?.name || baseSite.sourceId || '',
      sourceColor: getSourceColor(baseSite.sourceId),
      name: baseSite.title,
      sourceUrl: baseSite.sourceUrl,
      description: baseSite.description,
      thumbnailUrl: baseSite.image,
      siteType: baseSite.category,
      periodName: baseSite.period,
      periodStart: baseSite.periodStart,
      country: baseSite.location,
      lat: baseSite.coordinates[1],
      lon: baseSite.coordinates[0],
    }
    return [primary, ...alternates]
  }, [baseSite, alternates])

  // Reset override when the base site changes
  useEffect(() => setOverrideSite(null), [site?.id])

  // Use localSite from admin mode or the provided site, with override taking priority
  const displaySite = overrideSite || (isEmpireMode ? dummySite : adminMode.localSite)

  // Window management hook
  const windowHook = usePopupWindow({
    isStandalone,
    minimizedStackIndex,
    onMinimizedChange
  })

  // Reference links fetched from API (live from DB) — declared before gallery hook which depends on it
  const [apiReferenceLinks, setApiReferenceLinks] = useState<{ url: string; title: string; domain: string; kind: string }[] | undefined>(undefined)

  // Gallery data hook - use different hooks for site vs empire mode
  const [lng, lat] = displaySite.coordinates

  // Site gallery hook
  const siteGalleryHook = useGalleryData({
    siteId: displaySite.id,
    title: displaySite.title,
    location: displaySite.location,
    lat,
    lng,
    sourceUrl: displaySite.sourceUrl,
    thumbnailUrl: displaySite.image,
    isOffline,
    referenceLinks: apiReferenceLinks || displaySite.referenceLinks,
  })

  // Empire gallery hook - fetch images from Wikipedia and AWMC maps
  // Tries periodName first (e.g., "Roman Principate"), falls back to empireName (e.g., "Roman Empire")
  const empireGalleryHook = useEmpireGalleryData({
    empireId: empire?.id,
    empireName: empire?.name || '',
    periodName: currentPeriodName,
    wikiThumbnail: wikiSummary?.thumbnail,
    isOffline
  })

  // Both hooks return GalleryHookReturn - direct switch, no merge needed
  const galleryHook = isEmpireMode ? empireGalleryHook : siteGalleryHook

  // UI state
  const [shareSuccess, setShareSuccess] = useState(false)
  const [siteShareSuccess, setSiteShareSuccess] = useState(false)
  const [coordsCopied, setCoordsCopied] = useState(false)
  const [titleCopied, setTitleCopied] = useState(false)
  const [googleMapsLoaded, setGoogleMapsLoaded] = useState(false)
  const [googleMapsError, setGoogleMapsError] = useState(false)
  const [showStreetView, setShowStreetView] = useState(false)
  const [isMapFullscreen, setIsMapFullscreen] = useState(false)
  const mapSectionRef = useRef<HTMLDivElement>(null)

  // Lightbox state
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)
  const [lightboxItems, setLightboxItems] = useState<LightboxImage[]>([])
  const [isSettingHero, setIsSettingHero] = useState(false)

  // Model viewer state
  const [modelViewerIndex, setModelViewerIndex] = useState<number | null>(null)

  // Raw metadata for source-specific fields
  const [rawData, setRawData] = useState<Record<string, unknown> | null>(null)
  const [rawDataLoading, setRawDataLoading] = useState(false)

  // Track if tooltip was pinned by clicking minimized bar
  const tooltipPinnedRef = useRef(false)

  // Derived values
  const catColor = getCategoryColor(displaySite.category)
  const periodColor = PERIOD_COLORS[displaySite.period] || '#888'
  const sourceColor = getSourceColor(displaySite.sourceId)
  const sourceInfo = getSourceInfo(displaySite.sourceId)
  const sourceName = sourceInfo?.name || displaySite.sourceId

  // Detect underwater/water locations
  const isWaterLocation = useMemo(() => {
    const waterKeywords = ['sea', 'ocean', 'lake', 'underwater', 'submerged', 'sunken']
    const locationLower = (displaySite.location || '').toLowerCase()
    const titleLower = displaySite.title.toLowerCase()
    return waterKeywords.some(kw => locationLower.includes(kw) || titleLower.includes(kw))
  }, [displaySite.location, displaySite.title])

  // Handle fullscreen change events
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

  // Reset Street View when coordinates change
  useEffect(() => {
    setShowStreetView(false)
  }, [lat, lng])

  // Fetch rawData for all sources (button visibility controlled by data existence)
  useEffect(() => {
    if (isEmpireMode) return
    setRawDataLoading(true)
    setApiReferenceLinks(undefined)
    fetch(`${config.api.baseUrl}/sites/${displaySite.id}`)
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data?.rawData) {
          setRawData(data.rawData)
        }
        if (data?.referenceLinks) {
          setApiReferenceLinks(data.referenceLinks)
        }
      })
      .catch(err => {
        console.warn('Failed to fetch site rawData:', err)
      })
      .finally(() => setRawDataLoading(false))
  }, [displaySite.id, displaySite.sourceId, isEmpireMode])

  // Share URL — nginx serves dynamic OG tags to crawlers on site.html
  const shareUrl = `${window.location.origin}/site.html?id=${displaySite.id}`

  // Share site popup URL
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
      // User cancelled the share sheet — nothing to do
    }
  }

  // Share Google Maps location
  const googleMapsUrl = `https://www.google.com/maps/@${lat},${lng},15z/data=!3m1!1e3`
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
      // User cancelled the share sheet — nothing to do
    }
  }

  // Handle gallery item click
  const handleItemClick = (index: number) => {
    const items = galleryHook.currentItems

    // For 3D models, open the ModelViewer
    if (galleryHook.activeGalleryTab === '3dmodels') {
      setModelViewerIndex(index)
      return
    }

    // Use the unified adapter to convert items to lightbox format
    const lightboxImages = toLightboxImages(items)
    setLightboxItems(lightboxImages)
    setLightboxIndex(index)
  }

  // Handle setting a hero image via the lightbox
  const handleSetHero = useCallback(async (image: LightboxImage): Promise<boolean> => {
    if (!authToken || !isFounder || !displaySite.id) return false
    setIsSettingHero(true)
    try {
      const res = await fetch(`${config.api.baseUrl}/wiki-images/${displaySite.id}/set-hero`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          image_url: image.originalUrl || image.src,
          attribution_url: image.sourceUrl || '',
        }),
      })
      if (!res.ok) {
        const errText = await res.text().catch(() => '')
        console.error(`Set hero failed: ${res.status}`, errText)
        return false
      }
      const data = await res.json()
      if (data.path) {
        const newUrl = data.path + '?t=' + Date.now()
        galleryHook.setHeroImageSrc?.(newUrl)
        // Persist to site data so it survives popup close/reopen
        if (onSiteUpdate) {
          onSiteUpdate(displaySite.id, { ...displaySite, image: newUrl })
        }
      }
      return true
    } catch {
      return false
    } finally {
      setIsSettingHero(false)
    }
  }, [authToken, isFounder, displaySite.id])

  const handleRemoveImage = useCallback(async (image: LightboxImage): Promise<boolean> => {
    if (!authToken || !isFounder || !displaySite.id) return false
    try {
      const res = await fetch(`${config.api.baseUrl}/wiki-images/${displaySite.id}/remove-image`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ image_url: image.originalUrl || image.src }),
      })
      return res.ok
    } catch {
      return false
    }
  }, [authToken, isFounder, displaySite.id])

  // Popup content
  const popupContent = (
    <div
      ref={windowHook.popupRef}
      className={windowHook.windowClasses}
      style={windowHook.popupStyle}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Minimized bar */}
      {!isStandalone && windowHook.windowState === 'minimized' && (
        <MinimizedBar
          title={displaySite.title}
          siteId={displaySite.id}
          coordinates={displaySite.coordinates}
          isEmpireMode={isEmpireMode}
          onRestore={windowHook.handleMinimize}
          onClose={(e) => { e.stopPropagation(); onClose(); }}
          onHighlight={onHighlight}
          onSelect={onSelect}
          onFlyTo={onFlyTo}
          tooltipPinnedRef={tooltipPinnedRef}
        />
      )}

      {/* Window controls */}
      {!isStandalone && windowHook.windowState !== 'minimized' && (
        <WindowControls
          windowState={windowHook.windowState}
          siteId={displaySite.id}
          isEmpireMode={isEmpireMode}
          onMinimize={windowHook.handleMinimize}
          onMaximize={windowHook.handleMaximize}
          onClose={onClose}
        />
      )}

      {/* Standalone mode close button */}
      {isStandalone && (
        <div className="popup-standalone-close">
          <a
            className="popup-window-btn"
            href={`/site.html?id=${displaySite.id}`}
            target="_blank"
            rel="noopener noreferrer"
            title="Open full page"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <polyline points="15 3 21 3 21 9" />
              <line x1="10" y1="14" x2="21" y2="3" />
            </svg>
          </a>
          <button
            className="popup-window-btn close-btn"
            onClick={() => {
              if (onClose) onClose()
              else window.location.href = 'https://ancientnerds.com'
            }}
            title="Close"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
              <line x1="2" y1="2" x2="10" y2="10" />
              <line x1="10" y1="2" x2="2" y2="10" />
            </svg>
          </button>
        </div>
      )}

      {/* Resize handles */}
      {!isStandalone && windowHook.windowState === 'normal' && (
        <ResizeHandles onStartResize={windowHook.startResize} />
      )}

      <div className="popup-main-layout">
        {/* Left side - Content */}
        <div className="popup-content-side">
          <HeroHeader
            title={displaySite.title}
            heroImageSrc={galleryHook.heroImageSrc}
            isLoadingImages={galleryHook.isLoadingImages}
            isSettingHero={isSettingHero}
            sourceInfo={sourceInfo}
            sourceName={sourceName}
            sourceColor={sourceColor}
            sourceUrl={displaySite.sourceUrl}
            category={displaySite.category}
            period={displaySite.period}
            catColor={catColor}
            periodColor={periodColor}
            titleCopied={titleCopied}
            onTitleCopy={() => {
              navigator.clipboard.writeText(displaySite.title)
              setTitleCopied(true)
              setTimeout(() => setTitleCopied(false), 2000)
            }}
            onTitleBarMouseDown={!isStandalone ? windowHook.handleTitleBarMouseDown : undefined}
            onTitleBarDoubleClick={!isStandalone ? windowHook.handleTitleBarDoubleClick : undefined}
            isStandalone={isStandalone}
            windowState={windowHook.windowState}
            isEmpireMode={isEmpireMode}
            alternateSources={allSources}
            activeSiteId={displaySite.id}
            siteId={displaySite.id}
            onSourceSelect={(alt) => setOverrideSite(!alt || alt.id === baseSite.id ? null : alternateToSiteData(alt))}
            onAskLyra={onAskLyra ? () => {
              if (isEmpireMode && empire) {
                onAskLyra('empire', getSeshatPolityIdForYear(empire.id, empireYear) || empire.id, empireYear)
              } else if (site) {
                onAskLyra('site', site.id)
              }
            } : undefined}
            onShareSite={handleShareSite}
            siteShareSuccess={siteShareSuccess}
          />

          <div className="popup-body">
            <LocationSection
              location={displaySite.location}
              lat={lat}
              lng={lng}
              coordsCopied={coordsCopied}
              onCoordsCopy={() => {
                setCoordsCopied(true)
                setTimeout(() => setCoordsCopied(false), 2000)
              }}
              onSetProximity={onSetProximity}
              onMinimize={() => {
                windowHook.handleMinimize({ stopPropagation: () => {} } as React.MouseEvent)
              }}
            />

            {/* Admin Edit Mode */}
            {adminMode.isAdminMode && adminMode.editedSite ? (
              <AdminEditPanel
                site={adminMode.localSite}
                editedSite={adminMode.editedSite}
                onEditedSiteChange={adminMode.setEditedSite}
                saveError={adminMode.saveError}
                isSaving={adminMode.isSaving}
                onSave={adminMode.handleSave}
                onCancel={adminMode.handleCancelEdit}
              />
            ) : isEmpireMode ? (
              // Empire mode with Seshat data - tabbed interface
              <div className="empire-seshat-content">
                {/* Seshat Tabs */}
                <div className="empire-seshat-tabs">
                  <button
                    className={`empire-seshat-tab ${activeSeshatTab === 'overview' ? 'active' : ''}`}
                    onClick={() => setActiveSeshatTab('overview')}
                  >
                    Overview
                  </button>
                  <button
                    className={`empire-seshat-tab ${activeSeshatTab === 'stats' ? 'active' : ''}`}
                    onClick={() => setActiveSeshatTab('stats')}
                  >
                    Stats
                  </button>
                  <button
                    className={`empire-seshat-tab ${activeSeshatTab === 'military' ? 'active' : ''}`}
                    onClick={() => setActiveSeshatTab('military')}
                  >
                    Military
                  </button>
                  <button
                    className={`empire-seshat-tab ${activeSeshatTab === 'society' ? 'active' : ''}`}
                    onClick={() => setActiveSeshatTab('society')}
                  >
                    Society
                  </button>
                  <button
                    className={`empire-seshat-tab ${activeSeshatTab === 'history' ? 'active' : ''}`}
                    onClick={() => setActiveSeshatTab('history')}
                  >
                    History
                  </button>
                </div>

                {/* Tab Content */}
                <div className="empire-seshat-tab-content">
                  {activeSeshatTab === 'overview' && (
                    <div className="empire-overview-content">
                      {wikiLoading ? (
                        <div className="empire-loading">
                          <div className="empire-loading-spinner" />
                          <span>Loading description...</span>
                        </div>
                      ) : truncatedDescription ? (
                        <>
                          <p className="empire-wiki-description">{truncatedDescription}</p>
                          <div className="popup-links-section">
                            {empireWikipediaUrl && (
                              <a
                                href={empireWikipediaUrl}
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
                          </div>
                        </>
                      ) : (
                        <div className="empire-no-description">
                          <span>No description available</span>
                        </div>
                      )}
                    </div>
                  )}

                  {activeSeshatTab === 'stats' && seshatData && (
                    <EmpireStatsSection data={seshatData} />
                  )}

                  {activeSeshatTab === 'military' && seshatData && (
                    <EmpireWarfareSection warfare={seshatData.warfare} />
                  )}

                  {activeSeshatTab === 'society' && seshatData && (
                    <>
                      <EmpireSocialSection data={seshatData} />
                      <EmpireEconomySection data={seshatData} />
                    </>
                  )}

                  {activeSeshatTab === 'history' && seshatData && (
                    <>
                      <EmpireCrisisSection crisis={seshatData.crisis} />
                      <EmpireSuccessionSection
                        precedingPolities={seshatData.precedingPolities}
                        succeedingPolities={seshatData.succeedingPolities}
                      />
                    </>
                  )}

                  {!seshatData && activeSeshatTab !== 'overview' && (
                    <div className="empire-no-data">
                      {(() => {
                        const availablePeriods = empire ? getAvailablePeriodsForEmpire(empire.id) : []
                        if (availablePeriods.length > 0) {
                          return (
                            <>
                              <span className="empire-no-data-title">Data available for these periods:</span>
                              <div className="empire-available-periods">
                                {availablePeriods.map((period, idx) => (
                                  <button
                                    key={idx}
                                    className="empire-period-btn"
                                    onClick={() => onEmpireYearChange?.(period.yearStart)}
                                  >
                                    <span className="empire-period-name">{period.seshatName}</span>
                                    <span className="empire-period-years">
                                      {period.yearStart < 0 ? `${Math.abs(period.yearStart)} BCE` : `${period.yearStart} CE`}
                                      {' - '}
                                      {period.yearEnd < 0 ? `${Math.abs(period.yearEnd)} BCE` : `${period.yearEnd} CE`}
                                    </span>
                                  </button>
                                ))}
                              </div>
                            </>
                          )
                        }
                        return <span>No Seshat data available for this empire</span>
                      })()}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <DescriptionSection
                description={displaySite.description}
                sourceId={displaySite.sourceId}
                rawData={rawData}
                rawDataLoading={rawDataLoading}
                sourceUrl={displaySite.sourceUrl}
                onAdminClick={() => adminMode.enterAdminMode()}
                isEmpireMode={isEmpireMode}
                isFounder={isFounder}
                bestWikiUrl={displaySite.bestWikiUrl}
                sourceLanguage={displaySite.sourceLanguage}
                referenceLinks={apiReferenceLinks || displaySite.referenceLinks}
                descriptionCitations={displaySite.descriptionCitations}
              />
            )}

          </div>
        </div>

        {/* Right side - Map */}
        <div className="popup-maps-side">
          <MapSection
            lat={lat}
            lng={lng}
            location={displaySite.location}
            isWaterLocation={isWaterLocation}
            isEmpireMode={isEmpireMode}
            empire={empire}
            empireYear={empireYear}
            empireYearOptions={empireYearOptions}
            empireDefaultYear={empireDefaultYear}
            onEmpireYearChange={onEmpireYearChange}
            googleMapsLoaded={googleMapsLoaded}
            googleMapsError={googleMapsError}
            showStreetView={showStreetView}
            isMapFullscreen={isMapFullscreen}
            shareSuccess={shareSuccess}
            onGoogleMapsLoad={() => setGoogleMapsLoaded(true)}
            onGoogleMapsError={() => setGoogleMapsError(true)}
            onStreetViewToggle={() => { if (!showStreetView) reportAchievementEvent('street_view_opened'); setShowStreetView(!showStreetView) }}
            onFullscreenToggle={toggleMapFullscreen}
            onShareGoogleMaps={handleShareGoogleMaps}
            mapSectionRef={mapSectionRef}
          />
        </div>
      </div>

      {/* Gallery Section */}
      <div className={`popup-gallery-section ${galleryHook.isGalleryExpanded ? 'expanded' : ''}`}>
        {/* Expanded header */}
        {galleryHook.isGalleryExpanded && (
          <div
            className="gallery-expanded-header"
            onMouseDown={windowHook.handleTitleBarMouseDown}
            onDoubleClick={windowHook.handleTitleBarDoubleClick}
            style={{ cursor: windowHook.windowState !== 'maximized' ? 'move' : undefined }}
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

        {/* Gallery Tabs Bar — tabs scroll, toggle button always visible */}
        <div className="gallery-tabs-bar">
          <GalleryTabs
            activeTab={galleryHook.activeGalleryTab}
            onTabChange={galleryHook.setActiveGalleryTab}
            photoCount={galleryHook.photoItems.length}
            videoCount={galleryHook.videoItems.length}
            mapCount={galleryHook.mapItems.length}
            modelCount={galleryHook.sketchfabItems.length}
            artifactCount={galleryHook.artifactItems.length}
            bookCount={galleryHook.bookItems.length}
            paperCount={galleryHook.paperItems.length}
            referenceCount={galleryHook.referenceItems.length}
            isLoadingReferences={galleryHook.isLoadingReferences}
            webcamCount={galleryHook.webcamItems.length}
            storyCount={galleryHook.storiesItems.length}
            isLoadingStories={galleryHook.isLoadingStories}
            isLoadingWebcams={galleryHook.isLoadingWebcams}
            isLoadingImages={galleryHook.isLoadingImages}
            isLoadingVideos={galleryHook.isLoadingVideos}
            isLoadingMaps={galleryHook.isLoadingMaps}
            isLoadingModels={galleryHook.isLoadingModels}
            isLoadingArtifacts={galleryHook.isLoadingArtifacts}
            isLoadingBooks={galleryHook.isLoadingBooks}
            isLoadingPapers={galleryHook.isLoadingPapers}
          />
          <button
              className="gallery-toggle-btn"
              onClick={() => galleryHook.setIsGalleryExpanded(!galleryHook.isGalleryExpanded)}
              title={galleryHook.isGalleryExpanded ? 'Collapse gallery' : 'Expand gallery'}
            >
              {galleryHook.isGalleryExpanded ? (
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
        </div>

        {/* Gallery Content */}
        <GalleryContent
          activeTab={galleryHook.activeGalleryTab}
          items={galleryHook.currentItems}
          isLoading={galleryHook.isLoading}
          isOffline={isOffline}
          onItemClick={handleItemClick}
          isExpanded={galleryHook.isGalleryExpanded}
          sketchfabCategoryFilter={galleryHook.sketchfabCategoryFilter}
          onSketchfabCategoryFilterChange={galleryHook.setSketchfabCategoryFilter}
          storiesItems={galleryHook.storiesItems}
          isLoadingStories={galleryHook.isLoadingStories}
          referenceItems={galleryHook.referenceItems}
          isLoadingReferences={galleryHook.isLoadingReferences}
        />

        {/* Gallery Footer: Connector Status + Dev Warning */}
        <div className="gallery-footer">
          <ConnectorStatus
            sourcesSearched={galleryHook.sourcesSearched}
            sourcesFailed={galleryHook.sourcesFailed}
            itemsBySource={galleryHook.itemsBySource}
            searchTimeMs={galleryHook.searchTimeMs}
            isLoading={galleryHook.isLoading}
          />
          <div className="gallery-dev-warning">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
              <line x1="12" y1="9" x2="12" y2="13"></line>
              <line x1="12" y1="17" x2="12.01" y2="17"></line>
            </svg>
            <span>Beta - may show false positives</span>
          </div>
        </div>
      </div>
    </div>
  )

  // Lightbox portal
  const lightbox = lightboxIndex !== null && lightboxItems.length > 0 && createPortal(
    <ImageLightbox
      images={lightboxItems}
      currentIndex={lightboxIndex}
      onClose={() => setLightboxIndex(null)}
      onNavigate={setLightboxIndex}
      onSetHero={isFounder ? handleSetHero : undefined}
      onRemoveImage={isFounder ? handleRemoveImage : undefined}
    />,
    document.body
  )

  // Model viewer portal
  const modelViewer = modelViewerIndex !== null && galleryHook.sketchfabModels.length > 0 && createPortal(
    <ModelViewer
      models={galleryHook.sketchfabModels}
      currentIndex={modelViewerIndex}
      onClose={() => setModelViewerIndex(null)}
      onNavigate={setModelViewerIndex}
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
      </>
    )
  }

  // In windowed mode, render popup via portal
  return (
    <>
      {createPortal(popupContent, document.body)}
      {lightbox}
      {modelViewer}
    </>
  )
}

// Re-export types for backwards compatibility
export type { EmpirePopupData } from './types'
