/**
 * EmpireBordersPanel - Empire borders window with timeline controls
 * Floating window for historical empire border management
 */

import { EMPIRES, EMPIRE_REGIONS } from '../../../config/empireData'
import { formatYear } from '../../../utils/geoUtils'

interface EmpireBordersPanelProps {
  // Window state
  isOpen: boolean
  onClose: () => void
  height: number
  onHeightChange: (height: number) => void

  // Empire visibility
  visibleEmpires: Set<string>
  onToggleEmpire: (empireId: string) => void
  loadingEmpires: Set<string>

  // Empire year controls
  empireYears: Record<string, number>
  empireYearOptions: Record<string, number[]>
  empireDefaultYears: Record<string, number>
  onChangeEmpireYear: (empireId: string, year: number) => void
  onUpdateEmpireYearDisplay: (empireId: string, year: number) => void
  onEmpireYearSliderInput: (empireId: string, year: number) => void

  // Region expansion
  expandedRegions: Set<string>
  onToggleRegion: (region: string) => void

  // Labels and cities
  showEmpireLabels: boolean
  onToggleEmpireLabels: (show: boolean) => void
  showAncientCities: boolean
  onToggleAncientCities: (show: boolean) => void

  // Global timeline
  globalTimelineEnabled: boolean
  onToggleGlobalTimeline: (enabled: boolean) => void
  globalTimelineYear: number
  globalTimelineRange: { min: number; max: number }
  onGlobalTimelineYearChange: (year: number) => void
  onGlobalTimelineYearInput: (year: number) => void

  // Quick actions
  onSelectAll: () => void
  onSelectNone: () => void
  onSelectInvert: () => void
}

export function EmpireBordersPanel({
  isOpen,
  onClose,
  height,
  onHeightChange,
  visibleEmpires,
  onToggleEmpire,
  loadingEmpires,
  empireYears,
  empireYearOptions,
  empireDefaultYears,
  onChangeEmpireYear,
  onUpdateEmpireYearDisplay,
  onEmpireYearSliderInput,
  expandedRegions,
  onToggleRegion,
  showEmpireLabels,
  onToggleEmpireLabels,
  showAncientCities,
  onToggleAncientCities,
  globalTimelineEnabled,
  onToggleGlobalTimeline,
  globalTimelineYear,
  globalTimelineRange,
  onGlobalTimelineYearChange,
  onGlobalTimelineYearInput
}: EmpireBordersPanelProps) {
  if (!isOpen) return null

  const handleResizeStart = (e: React.MouseEvent) => {
    e.preventDefault()
    const startY = e.clientY
    const startHeight = height

    const onMove = (e: MouseEvent) => {
      const deltaY = startY - e.clientY
      onHeightChange(Math.max(150, Math.min(600, startHeight + deltaY)))
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  return (
    <div
      className="empire-borders-window"
      style={{ height }}
    >
      <div className="empire-borders-header">
        <div className="panel-label">Empire Borders</div>
        <button
          className="panel-close-btn"
          onClick={onClose}
          title="Close"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>

      {/* Options row: Show Labels + Cities + By Period toggles */}
      <div className="empire-options-row">
        <label className="layer-toggle">
          <input
            type="checkbox"
            checked={showEmpireLabels}
            onChange={(e) => onToggleEmpireLabels(e.target.checked)}
          />
          <span className="layer-label">Labels</span>
        </label>
        <label className="layer-toggle">
          <input
            type="checkbox"
            checked={showAncientCities}
            onChange={(e) => onToggleAncientCities(e.target.checked)}
          />
          <span className="layer-label">Cities</span>
        </label>
        <label className="layer-toggle">
          <input
            type="checkbox"
            checked={globalTimelineEnabled}
            onChange={(e) => onToggleGlobalTimeline(e.target.checked)}
          />
          <span className="layer-label">By Period</span>
        </label>
        <div className="empire-quick-btns">
          <button className="filter-btn" onClick={() => {
            EMPIRES.forEach(e => {
              if (!visibleEmpires.has(e.id)) onToggleEmpire(e.id)
            })
          }}>All</button>
          <button className="filter-btn" onClick={() => {
            EMPIRES.forEach(e => {
              if (visibleEmpires.has(e.id)) onToggleEmpire(e.id)
            })
          }}>None</button>
          <button className="filter-btn" onClick={() => {
            EMPIRES.forEach(e => onToggleEmpire(e.id))
          }}>Invert</button>
        </div>
      </div>

      {/* Global timeline slider (shown when By Period is enabled) */}
      {globalTimelineEnabled && (
        <div className="global-timeline-row">
          <input
            type="range"
            className="global-timeline-slider"
            min={globalTimelineRange.min}
            max={globalTimelineRange.max}
            step={1}
            value={globalTimelineYear}
            onInput={(e) => {
              const newYear = parseInt((e.target as HTMLInputElement).value)
              onGlobalTimelineYearInput(newYear)
            }}
            onMouseUp={(e) => onGlobalTimelineYearChange(parseInt((e.target as HTMLInputElement).value))}
            onTouchEnd={(e) => onGlobalTimelineYearChange(parseInt((e.target as HTMLInputElement).value))}
          />
          <span className="global-timeline-year">
            {formatYear(globalTimelineYear)}
          </span>
        </div>
      )}

      {/* Resize handle - vertical only */}
      <div
        className="empire-borders-resize-handle"
        onMouseDown={handleResizeStart}
      />

      {/* Empire list - scrollable */}
      <div className="empire-borders-list">
        {EMPIRE_REGIONS.map(region => (
          <div key={region} className="empire-region-compact">
            <div
              className="region-header-compact"
              onClick={() => onToggleRegion(region)}
            >
              <span className="region-chevron">{expandedRegions.has(region) ? '−' : '+'}</span>
              <span>{region}</span>
            </div>
            {expandedRegions.has(region) && (
              <div className="empire-list-compact">
                {EMPIRES.filter(e => e.region === region).map(empire => {
                  const isVisible = visibleEmpires.has(empire.id)
                  const yearOptions = empireYearOptions[empire.id] || []
                  const currentYear = empireYears[empire.id] || empire.startYear
                  const yearIndex = yearOptions.indexOf(currentYear)

                  // In global timeline mode, hide empires that don't exist at the current year
                  if (globalTimelineEnabled && isVisible) {
                    if (globalTimelineYear < empire.startYear || globalTimelineYear > empire.endYear) {
                      return null
                    }
                  }

                  return (
                    <label key={empire.id} className={`empire-row-inline ${isVisible ? 'active' : ''}`}>
                      <input
                        type="checkbox"
                        checked={isVisible}
                        onChange={() => onToggleEmpire(empire.id)}
                      />
                      <span
                        className="empire-color-dot"
                        style={{ backgroundColor: `#${empire.color.toString(16).padStart(6, '0')}` }}
                      />
                      <span className="empire-name-truncated" title={empire.name}>
                        {empire.name}
                      </span>
                      {/* Individual slider with year display - hidden when global timeline is enabled */}
                      {isVisible && yearOptions.length > 1 && !globalTimelineEnabled && (
                        <>
                          <span className="empire-year-display">{formatYear(currentYear)}</span>
                          <input
                            type="range"
                            className="empire-year-slider-inline"
                            min={0}
                            max={yearOptions.length - 1}
                            value={yearIndex >= 0 ? yearIndex : 0}
                            onClick={(e) => e.stopPropagation()}
                            onDoubleClick={() => {
                              const defaultYear = empireDefaultYears[empire.id]
                              if (defaultYear !== undefined) {
                                onUpdateEmpireYearDisplay(empire.id, defaultYear)
                                onChangeEmpireYear(empire.id, defaultYear)
                              }
                            }}
                            onInput={(e) => {
                              const year = yearOptions[parseInt((e.target as HTMLInputElement).value)]
                              onEmpireYearSliderInput(empire.id, year)
                            }}
                            onChange={(e) => {
                              const year = yearOptions[parseInt(e.target.value)]
                              onChangeEmpireYear(empire.id, year)
                            }}
                          />
                        </>
                      )}
                      {loadingEmpires.has(empire.id) && <span className="loading-dots">...</span>}
                    </label>
                  )
                })}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
