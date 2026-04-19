/**
 * HistoricalRoutesPanel - Historical routes window with trade routes and Roman roads
 * Floating window for historical route visualization management
 */

import { ROUTES, ROUTE_GROUPS, AWMC_ROADS_CONFIG, type RouteConfig } from '../../../config/routeData'

interface HistoricalRoutesPanelProps {
  // Window state
  isOpen: boolean
  onClose: () => void
  height: number
  onHeightChange: (height: number) => void
  width: number
  onWidthChange: (width: number) => void

  // Position (for drag repositioning)
  position: { x: number; y: number }
  onPositionChange: (pos: { x: number; y: number }) => void

  // Route visibility
  visibleRoutes: Set<string>
  onToggleRoute: (routeId: string) => void
  loadingRoutes: Set<string>

  // Group expansion
  expandedGroups: Set<string>
  onToggleGroup: (group: string) => void
}

export function HistoricalRoutesPanel({
  isOpen,
  onClose,
  height,
  onHeightChange,
  width,
  onWidthChange,
  position,
  onPositionChange,
  visibleRoutes,
  onToggleRoute,
  loadingRoutes,
  expandedGroups,
  onToggleGroup,
}: HistoricalRoutesPanelProps) {
  if (!isOpen) return null

  const MIN_WIDTH = 200
  const MIN_HEIGHT = 150

  const startResize = (e: React.MouseEvent, direction: string) => {
    e.preventDefault()
    e.stopPropagation()
    const startX = e.clientX
    const startY = e.clientY
    const startWidth = width
    const startHeight = height
    const startPos = { x: position.x, y: position.y }

    const onMove = (e: MouseEvent) => {
      const deltaX = e.clientX - startX
      const deltaY = e.clientY - startY

      let newWidth = startWidth
      let newHeight = startHeight
      let newX = startPos.x
      let newY = startPos.y

      if (direction.includes('e')) {
        newWidth = Math.max(MIN_WIDTH, startWidth + deltaX)
      }
      if (direction.includes('w')) {
        const widthChange = Math.min(deltaX, startWidth - MIN_WIDTH)
        newWidth = startWidth - widthChange
        newX = startPos.x + widthChange
      }
      if (direction.includes('s')) {
        newHeight = Math.max(MIN_HEIGHT, startHeight + deltaY)
      }
      if (direction.includes('n')) {
        const heightChange = Math.min(deltaY, startHeight - MIN_HEIGHT)
        newHeight = startHeight - heightChange
        newY = startPos.y - heightChange
      }

      onWidthChange(newWidth)
      onHeightChange(newHeight)
      onPositionChange({ x: newX, y: newY })
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  const handlePositionDragStart = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('.panel-close-btn')) return
    e.preventDefault()
    const startX = e.clientX
    const startY = e.clientY
    const startPos = { x: position.x, y: position.y }

    const onMove = (e: MouseEvent) => {
      const deltaX = e.clientX - startX
      const deltaY = e.clientY - startY
      onPositionChange({
        x: startPos.x + deltaX,
        y: startPos.y - deltaY,
      })
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  // All route IDs including AWMC
  const allRouteIds = [...ROUTES.map(r => r.id), AWMC_ROADS_CONFIG.id]

  const handleSelectAll = () => {
    allRouteIds.forEach(id => {
      if (!visibleRoutes.has(id)) onToggleRoute(id)
    })
  }

  const handleSelectNone = () => {
    allRouteIds.forEach(id => {
      if (visibleRoutes.has(id)) onToggleRoute(id)
    })
  }

  const handleSelectInvert = () => {
    allRouteIds.forEach(id => onToggleRoute(id))
  }

  return (
    <div
      className="historical-routes-window"
      style={{ width, height, '--routes-left': `${position.x}px`, '--routes-bottom': `${position.y}px` } as React.CSSProperties}
    >
      {/* 8-direction resize handles */}
      <div className="resize-n" onMouseDown={(e) => startResize(e, 'n')} />
      <div className="resize-s" onMouseDown={(e) => startResize(e, 's')} />
      <div className="resize-e" onMouseDown={(e) => startResize(e, 'e')} />
      <div className="resize-w" onMouseDown={(e) => startResize(e, 'w')} />
      <div className="resize-ne" onMouseDown={(e) => startResize(e, 'ne')} />
      <div className="resize-nw" onMouseDown={(e) => startResize(e, 'nw')} />
      <div className="resize-se" onMouseDown={(e) => startResize(e, 'se')} />
      <div className="resize-sw" onMouseDown={(e) => startResize(e, 'sw')} />

      <div className="empire-borders-header" onMouseDown={handlePositionDragStart}>
        <div className="panel-label">Historical Routes</div>
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

      {/* Quick actions row */}
      <div className="empire-options-row">
        <div className="empire-quick-btns">
          <button className="filter-btn" onClick={handleSelectAll}>All</button>
          <button className="filter-btn" onClick={handleSelectNone}>None</button>
          <button className="filter-btn" onClick={handleSelectInvert}>Invert</button>
        </div>
      </div>

      {/* Route list - scrollable */}
      <div className="empire-borders-list">
        {ROUTE_GROUPS.map(group => (
          <div key={group} className="empire-region-compact">
            <div
              className="region-header-compact"
              onClick={() => onToggleGroup(group)}
            >
              <span className="region-chevron">{expandedGroups.has(group) ? '−' : '+'}</span>
              <span>{group}</span>
            </div>
            {expandedGroups.has(group) && (
              <div className="empire-list-compact">
                {group === 'Roman Roads (AWMC)' ? (
                  // Single toggle for entire AWMC dataset
                  <label className={`empire-row-inline ${visibleRoutes.has(AWMC_ROADS_CONFIG.id) ? 'active' : ''}`}>
                    <input
                      type="checkbox"
                      checked={visibleRoutes.has(AWMC_ROADS_CONFIG.id)}
                      onChange={() => onToggleRoute(AWMC_ROADS_CONFIG.id)}
                    />
                    <span
                      className="empire-color-dot"
                      style={{ backgroundColor: `#${AWMC_ROADS_CONFIG.color.toString(16).padStart(6, '0')}` }}
                    />
                    <span className="empire-name-truncated" title={`${AWMC_ROADS_CONFIG.name} (${AWMC_ROADS_CONFIG.era})`}>
                      {AWMC_ROADS_CONFIG.name}
                    </span>
                    {loadingRoutes.has(AWMC_ROADS_CONFIG.id) && <span className="loading-dots">...</span>}
                  </label>
                ) : (
                  // Individual toggles for trade routes
                  ROUTES.map((route: RouteConfig) => (
                    <label key={route.id} className={`empire-row-inline ${visibleRoutes.has(route.id) ? 'active' : ''}`}>
                      <input
                        type="checkbox"
                        checked={visibleRoutes.has(route.id)}
                        onChange={() => onToggleRoute(route.id)}
                      />
                      <span
                        className="empire-color-dot"
                        style={{ backgroundColor: `#${route.color.toString(16).padStart(6, '0')}` }}
                      />
                      <span className="empire-name-truncated" title={`${route.name} (${route.era})`}>
                        {route.name}
                      </span>
                      {loadingRoutes.has(route.id) && <span className="loading-dots">...</span>}
                    </label>
                  ))
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
