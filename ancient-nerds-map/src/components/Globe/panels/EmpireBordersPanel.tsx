/**
 * EmpireBordersPanel - Empire borders window with timeline controls
 * Floating window for historical empire border management
 */

import { EMPIRES, EMPIRE_REGIONS } from '../../../config/empireData'
import { formatYear } from '../../../utils/geoUtils'
import { WindowFrame } from './WindowFrame'
import { useWindowDragResize } from '../../../hooks/globe/useWindowDragResize'

interface EmpireBordersPanelProps {
  isOpen: boolean
  onClose: () => void
  height: number
  onHeightChange: (height: number) => void
  width: number
  onWidthChange: (width: number) => void
  position: { x: number; y: number }
  onPositionChange: (pos: { x: number; y: number }) => void
  visibleEmpires: Set<string>
  onToggleEmpire: (empireId: string) => void
  loadingEmpires: Set<string>
  empireYears: Record<string, number>
  empireYearOptions: Record<string, number[]>
  empireDefaultYears: Record<string, number>
  onChangeEmpireYear: (empireId: string, year: number) => void
  onUpdateEmpireYearDisplay: (empireId: string, year: number) => void
  onEmpireYearSliderInput: (empireId: string, year: number) => void
  expandedRegions: Set<string>
  onToggleRegion: (region: string) => void
  globalTimelineEnabled: boolean
  onToggleGlobalTimeline: (enabled: boolean) => void
  globalTimelineYear: number
  globalTimelineRange: { min: number; max: number }
  onGlobalTimelineYearChange: (year: number) => void
  onGlobalTimelineYearInput: (year: number) => void
  onSelectAll: () => void
  onSelectNone: () => void
  onSelectInvert: () => void
  empireMetadata: Map<string, { startYear: number; endYear: number; defaultYear: number }>
}

export function EmpireBordersPanel({
  isOpen,
  onClose,
  height,
  onHeightChange,
  width,
  onWidthChange,
  position,
  onPositionChange,
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
  globalTimelineEnabled,
  onToggleGlobalTimeline,
  globalTimelineYear,
  globalTimelineRange,
  onGlobalTimelineYearChange,
  onGlobalTimelineYearInput,
  empireMetadata
}: EmpireBordersPanelProps) {
  const { startResize, handlePositionDragStart } = useWindowDragResize({
    position,
    width,
    height,
    onPositionChange,
    onWidthChange,
    onHeightChange,
  })

  if (!isOpen) return null

  return (
    <WindowFrame
      className="empire-borders-window"
      position={position}
      width={width}
      height={height}
      title="Empire Borders"
      onClose={onClose}
      dragResizeHandlers={{ startResize, handlePositionDragStart }}
      headerClassName="empire-borders-header"
    >
      <div className="empire-options-row">
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
                  const meta = empireMetadata.get(empire.id)
                  const currentYear = empireYears[empire.id] || meta?.startYear || yearOptions[0] || 0
                  const yearIndex = yearOptions.indexOf(currentYear)

                  if (globalTimelineEnabled && isVisible && meta) {
                    if (globalTimelineYear < meta.startYear || globalTimelineYear > meta.endYear) {
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
    </WindowFrame>
  )
}
