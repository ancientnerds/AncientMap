/**
 * MapLayersPanel - Vector layer toggles, base maps, and label controls
 * Left side panel for map layer management
 */

import type { ReactNode } from 'react'
import { LAYER_CONFIG, type VectorLayerKey, type VectorLayerVisibility } from '../../../config/vectorLayers'

interface MapLayersPanelProps {
  // Children (e.g., HistoricalLayersSection)
  children?: ReactNode
  // Panel state
  minimized: boolean
  onToggleMinimize: () => void

  // Tile layers (satellite/streets)
  tileLayers: { satellite: boolean; streets: boolean }
  onTileLayerToggle: (layer: 'satellite' | 'streets') => void

  // Vector layers
  vectorLayers: VectorLayerVisibility
  onVectorLayerToggle: (layer: VectorLayerKey) => void
  isLoadingLayers: Record<string, boolean>

  // Labels
  geoLabelsVisible: boolean
  onGeoLabelsToggle: () => void
  labelTypesExpanded: boolean
  onLabelTypesExpandToggle: () => void
  labelTypesVisible: Record<string, boolean>
  onLabelTypeToggle: (type: string) => void

  // Stars
  starsVisible: boolean
  onStarsToggle: () => void

  // Mapbox mode
  showMapbox: boolean

  // Offline availability
  isOffline: boolean
  cachedLayerIds: Set<string>
}

export function MapLayersPanel({
  children,
  minimized,
  onToggleMinimize,
  tileLayers,
  onTileLayerToggle,
  vectorLayers,
  onVectorLayerToggle,
  isLoadingLayers,
  geoLabelsVisible,
  onGeoLabelsToggle,
  labelTypesExpanded,
  onLabelTypesExpandToggle,
  labelTypesVisible,
  onLabelTypeToggle,
  starsVisible,
  onStarsToggle,
  showMapbox,
  isOffline,
  cachedLayerIds
}: MapLayersPanelProps) {
  return (
    <div className="layer-toggle-panel">
      <div className="vector-layers-section">
        <div className="panel-label-row">
          <div className="panel-label">Map Layers</div>
          <button
            className="panel-minimize-btn"
            onClick={onToggleMinimize}
            title={minimized ? "Maximize" : "Minimize"}
          >
            {minimized ? (
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="3" width="18" height="18" rx="2" />
              </svg>
            ) : (
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            )}
          </button>
        </div>
        {!minimized && (
          <>
            {/* Base Maps Section */}
            <div className="base-maps-section">
              <div className="subsection-label">Base Maps</div>
              <label className="layer-toggle">
                <input
                  type="checkbox"
                  checked={tileLayers.satellite}
                  onChange={() => onTileLayerToggle('satellite')}
                />
                <span
                  className="layer-color-indicator"
                  style={{ backgroundColor: '#2d5a27' }}
                />
                <span className="layer-label">Satellite</span>
              </label>
              <div className="labels-row">
                <label className={`layer-toggle ${showMapbox ? 'mapbox-unavailable' : ''}`} title={showMapbox ? 'Labels not available in Mapbox mode' : ''}>
                  <input
                    type="checkbox"
                    checked={geoLabelsVisible}
                    onChange={onGeoLabelsToggle}
                    disabled={showMapbox}
                  />
                  <span
                    className="layer-color-indicator"
                    style={{ backgroundColor: '#888899' }}
                  />
                  <span className="layer-label">Labels</span>
                </label>
                {geoLabelsVisible && !showMapbox && (
                  <button
                    className="label-expand-btn"
                    onClick={onLabelTypesExpandToggle}
                    title={labelTypesExpanded ? 'Collapse label types' : 'Expand label types'}
                  >
                    {labelTypesExpanded ? '▼' : '▶'}
                  </button>
                )}
              </div>
              {geoLabelsVisible && labelTypesExpanded && !showMapbox && (
                <div className="label-type-toggles">
                  {/* Sorted by priority (highest first) */}
                  {[
                    { key: 'continent', label: 'Continents', color: '#ffffff' },
                    { key: 'ocean', label: 'Oceans', color: '#a8d4ea' },
                    { key: 'country', label: 'Countries', color: '#f5f0e6' },
                    { key: 'sea', label: 'Seas', color: '#8ec4dc' },
                    { key: 'mountain', label: 'Mountains', color: '#c4a882' },
                    { key: 'desert', label: 'Deserts', color: '#d4b896' },
                    { key: 'capital', label: 'Capitals', color: '#F0E68C' },
                  ].map(({ key, label, color }) => (
                    <label key={key} className="label-type-toggle">
                      <input
                        type="checkbox"
                        checked={labelTypesVisible[key]}
                        onChange={() => onLabelTypeToggle(key)}
                      />
                      <span className="label-type-indicator" style={{ backgroundColor: color }} />
                      <span className="label-type-label">{label}</span>
                    </label>
                  ))}
                  <div className="label-type-group">
                    <span className="label-type-group-title">Features</span>
                    {[
                      { key: 'lake', label: 'Lakes', color: '#7cb8d8', layer: 'lakes' as VectorLayerKey },
                      { key: 'river', label: 'Rivers', color: '#8cc8e8', layer: 'rivers' as VectorLayerKey },
                      { key: 'plate', label: 'Tectonic Plates', color: '#FF6B6B', layer: 'plateBoundaries' as VectorLayerKey },
                      { key: 'glacier', label: 'Glaciers', color: '#88ddff', layer: 'glaciers' as VectorLayerKey },
                      { key: 'coralReef', label: 'Coral Reefs', color: '#ff6b9d', layer: 'coralReefs' as VectorLayerKey },
                    ].map(({ key, label, color, layer }) => (
                      <label
                        key={key}
                        className={`label-type-toggle ${!vectorLayers[layer] ? 'disabled' : ''}`}
                        title={!vectorLayers[layer] ? `Enable ${label.toLowerCase()} layer first` : ''}
                      >
                        <input
                          type="checkbox"
                          checked={labelTypesVisible[key] && vectorLayers[layer]}
                          onChange={() => onLabelTypeToggle(key)}
                          disabled={!vectorLayers[layer]}
                        />
                        <span className="label-type-indicator" style={{ backgroundColor: color }} />
                        <span className="label-type-label">{label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Vector Layers */}
            <div className={`subsection-label ${showMapbox ? 'mapbox-unavailable' : ''}`}>Vector Layers</div>
            {(Object.keys(LAYER_CONFIG) as VectorLayerKey[]).map(key => {
              // Check if layer is unavailable offline (only matters when trying to enable)
              const isLayerOfflineUnavailable = isOffline && !cachedLayerIds.has(key)
              const isCurrentlyEnabled = vectorLayers[key]
              // Only disable if trying to ENABLE when unavailable - always allow disabling
              // Also disable in Mapbox mode
              const shouldDisable = showMapbox || isLoadingLayers[key] || (isLayerOfflineUnavailable && !isCurrentlyEnabled)
              const unavailableClass = showMapbox ? 'mapbox-unavailable' : (isLayerOfflineUnavailable && !isCurrentlyEnabled ? 'offline-unavailable' : '')
              const tooltipText = showMapbox ? 'Vector layers not available in Mapbox mode' : (isLayerOfflineUnavailable && !isCurrentlyEnabled ? `${LAYER_CONFIG[key].label}: Not available offline. Download in Offline Manager or go online.` : LAYER_CONFIG[key].label)
              return (
                <label
                  key={key}
                  className={`layer-toggle ${unavailableClass}`}
                  title={tooltipText}
                >
                  <input
                    type="checkbox"
                    checked={isCurrentlyEnabled}
                    onChange={() => {
                      // Always allow unchecking, only block checking when unavailable
                      if (isCurrentlyEnabled || !isLayerOfflineUnavailable) {
                        onVectorLayerToggle(key)
                      }
                    }}
                    disabled={shouldDisable}
                  />
                  <span
                    className="layer-color-indicator"
                    style={{ backgroundColor: `#${LAYER_CONFIG[key].color.toString(16).padStart(6, '0')}` }}
                  />
                  <span className="layer-label">{LAYER_CONFIG[key].label}</span>
                  {isLoadingLayers[key] && <span className="loading-indicator">...</span>}
                </label>
              )
            })}
            <label className={`layer-toggle ${showMapbox ? 'mapbox-unavailable' : ''}`} title={showMapbox ? 'Stars not available in Mapbox mode' : ''}>
              <input
                type="checkbox"
                checked={starsVisible}
                onChange={onStarsToggle}
                disabled={showMapbox}
              />
              <span
                className="layer-color-indicator"
                style={{ backgroundColor: '#ffffff' }}
              />
              <span className="layer-label">Stars</span>
            </label>
            {children}
          </>
        )}
      </div>
    </div>
  )
}
