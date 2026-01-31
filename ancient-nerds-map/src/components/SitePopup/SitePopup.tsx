import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { SiteData, PERIOD_COLORS, getSourceColor, getCategoryColor, getSourceInfo } from '../../data/sites'
import type { GalleryImage } from '../ImageGallery'
import { config } from '../../config'
import { useOffline } from '../../contexts/OfflineContext'
import { hasMetadataFields } from '../../config/sourceFields'
import type { AncientMap } from '../../services/ancientMapsService'

// Wikipedia service for description
import { getEmpireWikipediaSummary, WikipediaSummary } from '../../services/wikipediaService'

// Seshat data service
import { getSeshatDataForEmpire, getWikipediaUrl, getSeshatPolityName } from '../../services/seshatService'
import { getAvailablePeriodsForEmpire } from '../../config/seshatMapping'
import type { SeshatPolityData } from '../../types/seshat'

// Components
import ImageLightbox, { LightboxImage } from '../ImageLightbox'
import ModelViewer from '../ModelViewer'
import PinAuthModal from '../PinAuthModal'

// Extracted components
import { usePopupWindow, WindowControls, ResizeHandles, MinimizedBar } from './window'
import { useGalleryData, useEmpireGalleryData, GalleryTabs, GalleryContent } from './gallery'
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

// Types
import type { SitePopupProps, EmpireSeshatTab } from './types'

export default function SitePopup({
  site,
  onClose,
  prefetchedImages,
  onSetProximity,
  onFlyTo,
  onHighlight,
  onSelect,
  isStandalone = false,
  onMinimizedChange,
  minimizedStackIndex = -1,
  isLoadingImages = false,
  onSiteUpdate,
  empire,
  empireYear,
  empireYearOptions,
  empireDefaultYear,
  onEmpireYearChange
}: SitePopupProps) {
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
    onSiteUpdate
  })

  // Use localSite from admin mode or the provided site
  const displaySite = isEmpireMode ? dummySite : adminMode.localSite

  // Window management hook
  const windowHook = usePopupWindow({
    isStandalone,
    minimizedStackIndex,
    onMinimizedChange
  })

  // Gallery data hook - use different hooks for site vs empire mode
  const [lng, lat] = displaySite.coordinates

  // Site gallery hook
  const siteGalleryHook = useGalleryData({
    title: displaySite.title,
    location: displaySite.location,
    lat,
    lng,
    prefetchedImages,
    isOffline,
    isLoadingImages
  })

  // Empire gallery hook - fetch images from Wikipedia and AWMC maps
  // Tries periodName first (e.g., "Roman Principate"), falls back to empireName (e.g., "Roman Empire")
  const empireGalleryHook = useEmpireGalleryData({
    empireId: empire?.id,
    empireName: empire?.name || '',
    periodName: currentPeriodName,
    isOffline
  })

  // Use the appropriate hook based on mode
  const galleryHook = isEmpireMode ? {
    ...empireGalleryHook,
    // Empire mode has photos, maps, artifacts (Smithsonian), and texts (Smithsonian)
    sketchfabItems: [],
    artifactItems: empireGalleryHook.artifactItems,
    artworkItems: [],
    textItems: empireGalleryHook.textItems,
    mythItems: [],
    ancientMapsLoading: empireGalleryHook.isLoadingMaps,
    sketchfabLoading: false,
    artifactsLoading: empireGalleryHook.isLoadingArtifacts,
    ancientMaps: empireGalleryHook.historicalMaps,
    sketchfabModels: [],
    artifacts: [],
    smithsonianArtifacts: empireGalleryHook.smithsonianArtifacts,
    heroImage: empireGalleryHook.heroImage ? {
      thumb: empireGalleryHook.heroImage.thumb,
      full: empireGalleryHook.heroImage.full,
      title: empireGalleryHook.heroImage.title,
      photographer: empireGalleryHook.heroImage.photographer,
      wikimediaUrl: empireGalleryHook.heroImage.wikimediaUrl,
      license: empireGalleryHook.heroImage.license
    } : null
  } : siteGalleryHook

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

  // Fetch rawData for sources with metadata fields
  useEffect(() => {
    if (!hasMetadataFields(displaySite.sourceId)) {
      setRawData(null)
      return
    }
    if (isEmpireMode) return
    setRawDataLoading(true)
    fetch(`${config.api.baseUrl}/sites/${displaySite.id}`)
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
  }, [displaySite.id, displaySite.sourceId, isEmpireMode])

  // Share URL with OG meta tags
  const shareUrl = `${config.api.baseUrl}/og/share/${displaySite.id}`

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
      console.log('Share cancelled')
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
      console.log('Share cancelled')
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
        const map = orig as AncientMap & { source?: string; license?: string; artist?: string; description?: string }
        // Check if this is a Wikimedia map (from empire gallery) vs David Rumsey (from site gallery)
        const isWikimedia = map.source === 'wikimedia'
        return {
          src: map.fullImage,
          title: map.title,
          photographer: isWikimedia ? (map.artist || 'Wikimedia Commons') : (map.date || undefined),
          sourceType: isWikimedia ? 'wikimedia' : 'david-rumsey',
          sourceUrl: map.webUrl,
          license: isWikimedia ? map.license : undefined
        }
      } else if (item.source === 'smithsonian') {
        const artifact = orig as { fullImage: string; title: string; date?: string; sourceUrl: string; museum?: string; license?: string }
        return {
          src: artifact.fullImage,
          title: artifact.title,
          photographer: artifact.museum || 'Smithsonian',
          sourceType: 'smithsonian',
          sourceUrl: artifact.sourceUrl,
          license: artifact.license
        }
      } else {
        const artifact = orig as { fullImage: string; title: string; date?: string; sourceUrl: string }
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
          onMinimize={windowHook.handleMinimize}
          onMaximize={windowHook.handleMaximize}
          onClose={onClose}
        />
      )}

      {/* Standalone mode close button */}
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
            isLoadingImages={isEmpireMode ? empireGalleryHook.isLoadingImages : isLoadingImages}
            sourceInfo={sourceInfo}
            sourceName={sourceName}
            sourceColor={sourceColor}
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
                onAdminClick={() => adminMode.setShowAdminPin(true)}
                isEmpireMode={isEmpireMode}
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
            siteShareSuccess={siteShareSuccess}
            onGoogleMapsLoad={() => setGoogleMapsLoaded(true)}
            onGoogleMapsError={() => setGoogleMapsError(true)}
            onStreetViewToggle={() => setShowStreetView(!showStreetView)}
            onFullscreenToggle={toggleMapFullscreen}
            onShareGoogleMaps={handleShareGoogleMaps}
            onShareSite={handleShareSite}
            siteId={displaySite.id}
            isStandalone={isStandalone}
            mapSectionRef={mapSectionRef}
          />
        </div>
      </div>

      {/* Gallery Section */}
      <div className={`popup-gallery-section ${galleryHook.isGalleryExpanded ? 'expanded' : ''}`}>
        {/* Collapse button */}
        {galleryHook.isGalleryExpanded && (
          <button
            className="gallery-collapse-btn"
            onClick={() => galleryHook.setIsGalleryExpanded(false)}
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

        {/* Expanded header */}
        {galleryHook.isGalleryExpanded && (
          <div
            className="gallery-expanded-header"
            onMouseDown={!isStandalone ? windowHook.handleTitleBarMouseDown : undefined}
            onDoubleClick={!isStandalone ? windowHook.handleTitleBarDoubleClick : undefined}
            style={{ cursor: !isStandalone && windowHook.windowState !== 'maximized' ? 'move' : undefined }}
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

        {/* Gallery Tabs */}
        <GalleryTabs
          activeTab={galleryHook.activeGalleryTab}
          onTabChange={galleryHook.setActiveGalleryTab}
          photoCount={galleryHook.photoItems.length}
          mapCount={galleryHook.mapItems.length}
          modelCount={galleryHook.sketchfabItems.length}
          artifactCount={galleryHook.artifactItems.length}
          artworkCount={galleryHook.artworkItems.length}
          textCount={galleryHook.textItems.length}
          mythCount={galleryHook.mythItems.length}
          isLoadingImages={isLoadingImages}
          isLoadingMaps={galleryHook.ancientMapsLoading}
          isLoadingModels={galleryHook.sketchfabLoading}
          isLoadingArtifacts={galleryHook.artifactsLoading}
          isLoadingTexts={isEmpireMode ? empireGalleryHook.isLoadingTexts : false}
          isGalleryExpanded={galleryHook.isGalleryExpanded}
          onExpandToggle={() => galleryHook.setIsGalleryExpanded(true)}
        />

        {/* Gallery Content */}
        <GalleryContent
          activeTab={galleryHook.activeGalleryTab}
          items={galleryHook.currentItems}
          isLoading={galleryHook.isLoading}
          isOffline={isOffline}
          onItemClick={handleItemClick}
        />
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

  // PIN auth modal portal
  const pinModal = adminMode.showAdminPin && !isEmpireMode && createPortal(
    <PinAuthModal
      isOpen={adminMode.showAdminPin}
      onClose={() => adminMode.setShowAdminPin(false)}
      onSuccess={adminMode.enterAdminMode}
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

  // In windowed mode, render popup via portal
  return (
    <>
      {createPortal(popupContent, document.body)}
      {lightbox}
      {modelViewer}
      {pinModal}
    </>
  )
}

// Re-export types for backwards compatibility
export type { EmpirePopupData } from './types'
