/**
 * HistoricalLayersSection - Toggles for Geological, Empire Borders, and Historical Routes
 * Each toggle opens its respective floating window panel
 */

interface HistoricalLayersSectionProps {
  // Geological Layers toggle
  hasActiveGeologicalLayers: boolean
  onGeologicalLayersToggle: () => void

  // Empire Borders toggle
  empireBordersWindowOpen: boolean
  hasVisibleEmpires: boolean
  onEmpireBordersToggle: () => void

  // Historical Routes toggle
  hasVisibleRoutes: boolean
  onHistoricalRoutesToggle: () => void
}

export function HistoricalLayersSection({
  hasActiveGeologicalLayers,
  onGeologicalLayersToggle,
  empireBordersWindowOpen: _empireBordersWindowOpen,
  hasVisibleEmpires,
  onEmpireBordersToggle,
  hasVisibleRoutes,
  onHistoricalRoutesToggle,
}: HistoricalLayersSectionProps) {
  return (
    <div className="sea-level-section">
      <div className="panel-label">Historical Layers</div>

      {/* Geological Layers toggle — opens floating window */}
      <label className="layer-toggle">
        <input
          type="checkbox"
          checked={hasActiveGeologicalLayers}
          onChange={onGeologicalLayersToggle}
        />
        <span
          className="layer-color-indicator"
          style={{ backgroundColor: '#8B4513' }}
        />
        <span className="layer-label">Geological Layers</span>
      </label>

      {/* Empire Borders toggle */}
      <label className="layer-toggle">
        <input
          type="checkbox"
          checked={hasVisibleEmpires}
          onChange={onEmpireBordersToggle}
        />
        <span
          className="layer-color-indicator"
          style={{ backgroundColor: '#FF7777' }}
        />
        <span className="layer-label">Empire Borders</span>
      </label>

      {/* Historical Routes toggle */}
      <label className="layer-toggle">
        <input
          type="checkbox"
          checked={hasVisibleRoutes}
          onChange={onHistoricalRoutesToggle}
        />
        <span className="layer-color-indicator" style={{ backgroundColor: '#DAA520' }} />
        <span className="layer-label">Historical Routes</span>
      </label>
    </div>
  )
}
