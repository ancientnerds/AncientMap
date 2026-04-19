/**
 * GeologicalLayersSection - Floating window for paleoshoreline and North Sea geological overlays
 * Follows the EmpireBordersPanel pattern: toggle in MapLayersPanel opens this floating window
 */

import { useState } from 'react'
import { reportAchievementEvent } from '../../../utils/cardApi'
import {
  GEOLOGICAL_LAYER_CONFIG,
  GEOLOGICAL_GROUPS,
  type GeologicalLayerKey,
  type GeologicalLayerVisibility,
} from '../../../config/geologicalLayers'

interface GeologicalLayersPanelProps {
  // Window state
  isOpen: boolean
  onClose: () => void
  height: number
  onHeightChange: (height: number) => void

  // Position (for drag repositioning)
  position: { x: number; y: number }
  onPositionChange: (pos: { x: number; y: number }) => void

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

  // Geological overlays
  geologicalLayers: GeologicalLayerVisibility
  onGeologicalLayerToggle: (key: GeologicalLayerKey) => void
  isLoadingGeological: Partial<Record<GeologicalLayerKey, boolean>>

  // Mapbox mode
  showMapbox: boolean
}

export function GeologicalLayersSection({
  isOpen,
  onClose,
  height,
  onHeightChange,
  position,
  onPositionChange,
  paleoshorelineVisible,
  onPaleoshorelineToggle,
  isLoadingPaleoshoreline,
  seaLevel,
  sliderSeaLevel,
  onSeaLevelChange,
  onSliderSeaLevelChange,
  replaceCoastlines,
  onReplaceCoastlinesChange,
  geologicalLayers,
  onGeologicalLayerToggle,
  isLoadingGeological,
  showMapbox,
}: GeologicalLayersPanelProps) {
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())

  if (!isOpen) return null

  const toggleGroup = (group: string) => {
    setExpandedGroups(prev => {
      const next = new Set(prev)
      if (next.has(group)) next.delete(group)
      else next.add(group)
      return next
    })
  }

  const handleResizeStart = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const startY = e.clientY
    const startHeight = height

    const onMove = (e: MouseEvent) => {
      const deltaY = startY - e.clientY
      onHeightChange(Math.max(150, Math.min(600, startHeight - deltaY)))
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  const handleTopResizeStart = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
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
        x: startPos.x - deltaX,
        y: startPos.y + deltaY,
      })
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
      className="empire-borders-window geological-layers-window"
      style={{ height, '--geological-right-offset': `${position.x}px`, '--geological-bottom-offset': `${position.y}px` } as React.CSSProperties}
    >
      <div className="empire-borders-header" onMouseDown={handlePositionDragStart}>
        <div className="panel-label">Geological Layers</div>
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

      {/* Resize handle - top */}
      <div
        className="empire-borders-resize-handle empire-borders-resize-handle-top"
        onMouseDown={handleTopResizeStart}
      />

      <div className="empire-borders-list">
        {/* Paleoshoreline toggle — disabled in Mapbox (3D contour lines don't render on Mapbox) */}
        <label className={`layer-toggle ${showMapbox ? 'mapbox-unavailable' : ''}`}>
          <input
            type="checkbox"
            checked={paleoshorelineVisible}
            onChange={() => { onPaleoshorelineToggle(); if (!paleoshorelineVisible) reportAchievementEvent('sea_level_adjusted') }}
            disabled={isLoadingPaleoshoreline || showMapbox}
          />
          <span
            className="layer-color-indicator"
            style={{ backgroundColor: '#8B4513' }}
          />
          <span className="layer-label">Paleoshoreline</span>
          {isLoadingPaleoshoreline && <span className="loading-indicator">...</span>}
        </label>

        {/* Sea level controls */}
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

        {/* North Sea Overlays */}
        <div className="subsection-label" style={{ marginTop: 8 }}>North Sea Overlays</div>

        {GEOLOGICAL_GROUPS.map(({ group, label, layers }) => {
          const isExpanded = expandedGroups.has(group)
          const activeCount = layers.filter(k => geologicalLayers[k]).length
          return (
            <div key={group}>
              <button
                className="geological-group-header"
                onClick={() => toggleGroup(group)}
              >
                <span className="region-chevron">{isExpanded ? '−' : '+'}</span>
                <span>{label} ({layers.length})</span>
                {activeCount > 0 && <span className="geological-group-active">{activeCount} on</span>}
              </button>
              {isExpanded && (
                <div className="geological-group-content">
                  {layers.map(layerKey => {
                    const cfg = GEOLOGICAL_LAYER_CONFIG[layerKey]
                    const isLoading = isLoadingGeological[layerKey]
                    return (
                      <label key={layerKey} className="layer-toggle">
                        <input
                          type="checkbox"
                          checked={geologicalLayers[layerKey]}
                          onChange={() => onGeologicalLayerToggle(layerKey)}
                          disabled={isLoading}
                        />
                        <span
                          className="layer-color-indicator"
                          style={{ backgroundColor: `#${cfg.color.toString(16).padStart(6, '0')}` }}
                        />
                        <span className="layer-label">{cfg.label}</span>
                        {isLoading && <span className="loading-indicator">...</span>}
                      </label>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Resize handle - bottom */}
      <div className="empire-borders-resize-handle" onMouseDown={handleResizeStart} />
    </div>
  )
}
