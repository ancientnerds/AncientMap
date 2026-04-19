/**
 * HistoricalRoutesPanel - Historical routes window with trade routes and Roman roads
 * Floating window for historical route visualization management
 */

import { ROUTES, ROUTE_GROUPS, AWMC_ROADS_CONFIG, type RouteConfig } from '../../../config/routeData'
import { WindowFrame } from './WindowFrame'
import { useWindowDragResize } from '../../../hooks/globe/useWindowDragResize'

interface HistoricalRoutesPanelProps {
  isOpen: boolean
  onClose: () => void
  height: number
  onHeightChange: (height: number) => void
  width: number
  onWidthChange: (width: number) => void
  position: { x: number; y: number }
  onPositionChange: (pos: { x: number; y: number }) => void
  visibleRoutes: Set<string>
  onToggleRoute: (routeId: string) => void
  loadingRoutes: Set<string>
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
  const { startResize, handlePositionDragStart } = useWindowDragResize({
    position,
    width,
    height,
    onPositionChange,
    onWidthChange,
    onHeightChange,
  })

  if (!isOpen) return null

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
    <WindowFrame
      className="historical-routes-window"
      position={position}
      width={width}
      height={height}
      title="Historical Routes"
      onClose={onClose}
      dragResizeHandlers={{ startResize, handlePositionDragStart }}
      headerClassName="empire-borders-header"
    >
      <div className="empire-options-row">
        <div className="empire-quick-btns">
          <button className="filter-btn" onClick={handleSelectAll}>All</button>
          <button className="filter-btn" onClick={handleSelectNone}>None</button>
          <button className="filter-btn" onClick={handleSelectInvert}>Invert</button>
        </div>
      </div>

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
    </WindowFrame>
  )
}
