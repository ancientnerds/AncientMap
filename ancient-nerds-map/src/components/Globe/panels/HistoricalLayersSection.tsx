/**
 * HistoricalLayersSection - Paleoshoreline and Empire Borders controls
 * Part of the Map Layers panel for historical visualization features
 */

interface HistoricalLayersSectionProps {
  // Paleoshoreline
  paleoshorelineVisible: boolean
  onPaleoshorelineToggle: () => void
  isLoadingPaleoshoreline: boolean
  seaLevel: number
  sliderSeaLevel: number
  onSeaLevelChange: (level: number) => void
  onSliderSeaLevelChange: (level: number) => void
  replaceCoastlines: boolean
  onReplaceCoastlinesChange: (replace: boolean) => void

  // Empire Borders toggle
  empireBordersWindowOpen: boolean
  onEmpireBordersToggle: () => void

  // Mapbox mode (disables 3D layers)
  showMapbox: boolean
}

export function HistoricalLayersSection({
  paleoshorelineVisible,
  onPaleoshorelineToggle,
  isLoadingPaleoshoreline,
  seaLevel,
  sliderSeaLevel,
  onSeaLevelChange,
  onSliderSeaLevelChange,
  replaceCoastlines,
  onReplaceCoastlinesChange,
  empireBordersWindowOpen,
  onEmpireBordersToggle,
  showMapbox
}: HistoricalLayersSectionProps) {
  return (
    <div className="sea-level-section">
      <div className="panel-label">Historical Layers</div>

      {/* Paleoshoreline toggle - unavailable in Mapbox mode (3D layer) */}
      <label className={`layer-toggle ${showMapbox ? 'mapbox-unavailable' : ''}`}>
        <input
          type="checkbox"
          checked={paleoshorelineVisible}
          onChange={onPaleoshorelineToggle}
          disabled={isLoadingPaleoshoreline || showMapbox}
        />
        <span
          className="layer-color-indicator"
          style={{ backgroundColor: '#8B4513' }}
        />
        <span className="layer-label">Paleoshoreline</span>
        {isLoadingPaleoshoreline && <span className="loading-indicator">...</span>}
      </label>

      {/* Sea level display and slider */}
      {paleoshorelineVisible && (
        <div className="sea-level-controls">
          <div className="sea-level-value">
            <button
              className="sea-level-btn"
              onClick={() => {
                const newVal = Math.max(-150, sliderSeaLevel - 1)
                onSliderSeaLevelChange(newVal)
                onSeaLevelChange(newVal)
              }}
              disabled={sliderSeaLevel <= -150}
            >
              −
            </button>
            <input
              type="number"
              className="sea-level-input"
              min={-150}
              max={-1}
              step={1}
              value={sliderSeaLevel}
              onChange={(e) => {
                const val = parseInt(e.target.value) || 0
                const clamped = Math.max(-150, Math.min(-1, val))
                onSliderSeaLevelChange(clamped)
              }}
              onBlur={(e) => {
                const val = parseInt(e.target.value) || 0
                const clamped = Math.max(-150, Math.min(-1, val))
                onSliderSeaLevelChange(clamped)
                onSeaLevelChange(clamped)
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  const val = parseInt((e.target as HTMLInputElement).value) || 0
                  const clamped = Math.max(-150, Math.min(-1, val))
                  onSliderSeaLevelChange(clamped)
                  onSeaLevelChange(clamped)
                }
              }}
            />
            <span className="sea-level-unit">m</span>
            <button
              className="sea-level-btn"
              onClick={() => {
                const newVal = Math.min(-1, sliderSeaLevel + 1)
                onSliderSeaLevelChange(newVal)
                onSeaLevelChange(newVal)
              }}
              disabled={sliderSeaLevel >= -1}
            >
              +
            </button>
          </div>

          <input
            type="range"
            className="sea-level-slider"
            min={-150}
            max={-1}
            step={1}
            value={sliderSeaLevel}
            onChange={(e) => onSliderSeaLevelChange(Number(e.target.value))}
            onMouseUp={(e) => onSeaLevelChange(Number((e.target as HTMLInputElement).value))}
            onTouchEnd={(e) => onSeaLevelChange(Number((e.target as HTMLInputElement).value))}
          />

          <div className="sea-level-presets">
            <button
              className={`preset-btn ${seaLevel === -120 ? 'active' : ''}`}
              onClick={() => { onSliderSeaLevelChange(-120); onSeaLevelChange(-120) }}
              title="Last Glacial Maximum (~20,000 years ago)"
            >
              LGM
            </button>
            <button
              className={`preset-btn ${seaLevel === -1 ? 'active' : ''}`}
              onClick={() => { onSliderSeaLevelChange(-1); onSeaLevelChange(-1) }}
              title="Near present day (-1m)"
            >
              -1m
            </button>
          </div>

          <label className="replace-coastlines-toggle">
            <input
              type="checkbox"
              checked={replaceCoastlines}
              onChange={(e) => onReplaceCoastlinesChange(e.target.checked)}
            />
            <span>Replace Coastlines</span>
          </label>
        </div>
      )}

      {/* Empire Borders toggle */}
      <label className="layer-toggle">
        <input
          type="checkbox"
          checked={empireBordersWindowOpen}
          onChange={onEmpireBordersToggle}
        />
        <span
          className="layer-color-indicator"
          style={{ backgroundColor: '#FF7777' }}
        />
        <span className="layer-label">Empire Borders</span>
      </label>
    </div>
  )
}
