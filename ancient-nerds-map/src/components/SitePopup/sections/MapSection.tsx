import { useMemo, useState, useEffect, useRef } from 'react'
import { getStreetViewEmbedUrl } from '../../../services/streetViewService'
import EmpireMinimap from '../../EmpireMinimap'
import { getAvailablePeriodsForEmpire } from '../../../config/seshatMapping'
import type { MapSectionProps } from '../types'

// Format year for display (handles BC/AD)
function formatYearDisplay(year: number): string {
  if (year < 0) {
    return `${Math.abs(year)} BC`
  }
  return `${year} AD`
}

// Format year range - only show era on start if different from end
function formatYearRange(startYear: number, endYear: number): string {
  const startEra = startYear < 0 ? 'BC' : 'AD'
  const endEra = endYear < 0 ? 'BC' : 'AD'
  const startNum = Math.abs(startYear)
  const endNum = Math.abs(endYear)

  if (startEra === endEra) {
    return `${startNum}–${endNum} ${endEra}`
  }
  return `${startNum} ${startEra}–${endNum} ${endEra}`
}

export function MapSection({
  lat,
  lng,
  isWaterLocation,
  isEmpireMode,
  empire,
  empireYear,
  empireYearOptions,
  empireDefaultYear,
  onEmpireYearChange,
  googleMapsLoaded,
  googleMapsError,
  showStreetView,
  isMapFullscreen,
  shareSuccess,
  siteShareSuccess,
  onGoogleMapsLoad,
  onGoogleMapsError,
  onStreetViewToggle,
  onFullscreenToggle,
  onShareGoogleMaps,
  onShareSite,
  siteId,
  isStandalone = false,
  mapSectionRef
}: MapSectionProps) {
  // Google Maps URLs - zoomed out 3 steps (18 -> 15)
  const googleMapsUrl = `https://www.google.com/maps/@${lat},${lng},15z/data=!3m1!1e3`
  const googleMapsEmbedUrl = `https://www.google.com/maps/embed?pb=!1m14!1m12!1m3!1d4000!2d${lng}!3d${lat}!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!5e1!3m2!1sen!2sus!4v1234567890`
  const streetViewEmbedUrl = getStreetViewEmbedUrl(lat, lng)

  // URL to open standalone popup in new tab (direct SPA link)
  const sitePopupUrl = `${window.location.origin}${window.location.pathname}?site=${siteId}`

  // Get period mappings for this empire
  const periods = useMemo(() => {
    if (!empire) return []
    return getAvailablePeriodsForEmpire(empire.id)
  }, [empire?.id])

  // Calculate which period is currently active
  const currentYear = empireYear || empire?.peakYear || empire?.startYear || 0
  const activePeriodIndex = useMemo(() => {
    if (!periods.length) return -1
    // Search from end so later periods take priority at boundaries
    // (e.g., -664 is both end of Third Intermediate and start of Late Period)
    for (let i = periods.length - 1; i >= 0; i--) {
      if (currentYear >= periods[i].yearStart && currentYear <= periods[i].yearEnd) {
        return i
      }
    }
    return -1
  }, [periods, currentYear])

  // Animated slider position state (for empire mode)
  const [animatedSliderValue, setAnimatedSliderValue] = useState(0)
  const animationRef = useRef<number | null>(null)
  const isUserDragging = useRef(false)
  const skipNextAnimation = useRef(false)
  const lastMouseDownTime = useRef(0)
  const ignoreInputUntil = useRef(0)

  // Calculate target year index for empire slider (computed outside conditional for hooks)
  const yearOptions = empireYearOptions || []
  const targetYearIndex = useMemo(() => {
    if (!isEmpireMode || !empire || yearOptions.length === 0) return 0
    return yearOptions.reduce((closestIdx, year, idx) => {
      const closestDiff = Math.abs(yearOptions[closestIdx] - currentYear)
      const currentDiff = Math.abs(year - currentYear)
      return currentDiff < closestDiff ? idx : closestIdx
    }, 0)
  }, [isEmpireMode, empire, yearOptions, currentYear])

  // Animate slider to target position with ease-out
  useEffect(() => {
    if (!isEmpireMode || !empire) return
    if (isUserDragging.current) return // Don't animate while user is dragging

    // Skip animation if flagged (e.g., during double-click jump)
    if (skipNextAnimation.current) {
      skipNextAnimation.current = false
      setAnimatedSliderValue(targetYearIndex)
      return
    }

    const startValue = animatedSliderValue
    const endValue = targetYearIndex
    if (Math.abs(startValue - endValue) < 0.01) return

    const duration = 300 // ms
    const startTime = performance.now()

    // Ease-out cubic function
    const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3)

    const animate = (currentTime: number) => {
      const elapsed = currentTime - startTime
      const progress = Math.min(elapsed / duration, 1)
      const easedProgress = easeOutCubic(progress)

      const newValue = startValue + (endValue - startValue) * easedProgress
      setAnimatedSliderValue(newValue)

      if (progress < 1) {
        animationRef.current = requestAnimationFrame(animate)
      }
    }

    animationRef.current = requestAnimationFrame(animate)

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [targetYearIndex, isEmpireMode, empire])

  if (isEmpireMode && empire) {
    // Empire mode: Interactive minimap with empire boundaries and period timeline
    return (
      <div className="empire-minimap-section">
        <EmpireMinimap
          empireId={empire.id}
          year={empireYear || empire.startYear}
          empireColor={empire.color}
        />

        {/* Period Timeline with Slider */}
        {onEmpireYearChange ? (
          <div className="empire-period-timeline">
            {/* Year Slider */}
            {yearOptions.length > 1 && (
              <div
                className="empire-year-slider-row"
                title={`Double-click to jump to default year (${empireDefaultYear ? formatYearDisplay(empireDefaultYear) : 'start year'})`}
              >
                <input
                  type="range"
                  className="empire-popup-year-slider"
                  min={0}
                  max={yearOptions.length - 1}
                  value={Math.round(animatedSliderValue)}
                  onClick={(e) => e.stopPropagation()}
                  onMouseDown={() => {
                    const now = Date.now()
                    // Detect double-click early (second mousedown within 300ms)
                    if (now - lastMouseDownTime.current < 300) {
                      // This is a double-click - block input events and jump to default year
                      ignoreInputUntil.current = now + 300

                      const defaultYear = empireDefaultYear ?? empire.startYear
                      if (defaultYear !== undefined && yearOptions.length > 0) {
                        // Cancel any running animation
                        if (animationRef.current) {
                          cancelAnimationFrame(animationRef.current)
                          animationRef.current = null
                        }

                        // Find the index for default year
                        const defaultIndex = yearOptions.reduce((closestIdx, year, idx) => {
                          const closestDiff = Math.abs(yearOptions[closestIdx] - defaultYear)
                          const currentDiff = Math.abs(year - defaultYear)
                          return currentDiff < closestDiff ? idx : closestIdx
                        }, 0)

                        // Skip animation and directly jump
                        skipNextAnimation.current = true
                        setAnimatedSliderValue(defaultIndex)
                        onEmpireYearChange(defaultYear)
                      }
                      lastMouseDownTime.current = 0
                      return
                    }
                    lastMouseDownTime.current = now
                    isUserDragging.current = true
                  }}
                  onMouseUp={() => { isUserDragging.current = false }}
                  onTouchStart={() => { isUserDragging.current = true }}
                  onTouchEnd={() => { isUserDragging.current = false }}
                  onInput={(e) => {
                    // Ignore input during double-click handling
                    if (Date.now() < ignoreInputUntil.current) return
                    const idx = parseInt((e.target as HTMLInputElement).value)
                    setAnimatedSliderValue(idx)
                  }}
                  onChange={(e) => {
                    // Ignore change during double-click handling
                    if (Date.now() < ignoreInputUntil.current) return
                    const idx = parseInt(e.target.value)
                    const year = yearOptions[idx]
                    if (year !== undefined) {
                      onEmpireYearChange(year)
                    }
                  }}
                />
                <span className="empire-year-display">{formatYearDisplay(currentYear)}</span>
              </div>
            )}

            {/* Period Buttons - only show periods that have data */}
            {periods.length > 0 && (
              <div className="empire-period-segments">
                {periods.map((period, index) => {
                  const isActive = index === activePeriodIndex
                  // Check if we have any data for this period
                  const hasData = yearOptions.some(
                    y => y >= period.yearStart && y <= period.yearEnd
                  )
                  // Skip periods without data
                  if (!hasData) return null

                  return (
                    <button
                      key={period.seshatId}
                      className={`empire-period-segment ${isActive ? 'active' : ''}`}
                      onClick={() => {
                        // Find last year in this period (shows maximum extent)
                        const yearsInPeriod = yearOptions.filter(
                          y => y >= period.yearStart && y <= period.yearEnd
                        )
                        if (yearsInPeriod.length > 0) {
                          onEmpireYearChange(yearsInPeriod[yearsInPeriod.length - 1])
                        }
                      }}
                      title={`${period.seshatName}\n${formatYearDisplay(period.yearStart)} - ${formatYearDisplay(period.yearEnd)}`}
                    >
                      <span className="segment-name">{period.seshatName}</span>
                      <span className="segment-years">
                        {formatYearRange(period.yearStart, period.yearEnd)}
                      </span>
                    </button>
                  )
                })}
              </div>
            )}

          </div>
        ) : null}
      </div>
    )
  }

  // Site mode: Google Maps satellite view
  return (
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
              onLoad={onGoogleMapsLoad}
              onError={onGoogleMapsError}
            />
          )}
        </div>
      )}
      <div className="map-buttons-bar">
        {/* Fullscreen toggle button */}
        <button
          className={`map-action-btn fullscreen-toggle ${isMapFullscreen ? 'active' : ''}`}
          onClick={onFullscreenToggle}
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
          onClick={onShareSite}
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
          onClick={onStreetViewToggle}
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
          onClick={onShareGoogleMaps}
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
  )
}
