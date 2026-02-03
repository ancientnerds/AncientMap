/**
 * OptionsPanel - HUD settings, dot size, tooltips, and action buttons
 * Top-right info panel with various controls and indicators
 */

import { forwardRef } from 'react'
import { FpsDisplay } from './FpsDisplay'
import type { StatusSummary } from '../../../types/connectors'

interface OptionsPanelProps {
  // Display toggles
  showTooltips: boolean
  onToggleTooltips: () => void
  showCoordinates: boolean
  onToggleCoordinates: () => void
  showScale: boolean
  onToggleScale: () => void

  // HUD scale
  hudScale: number
  hudScalePreview: number | null
  onHudScaleChange: (value: number) => void
  onHudScalePreviewChange: (value: number | null) => void

  // Dot size
  dotSize: number
  onDotSizeChange: (size: number) => void

  // HUD visibility
  onHideHud: () => void
  onScreenshot: () => void

  // Selection undo/redo
  canUndoSelection?: boolean
  onUndoSelection?: () => void
  canRedoSelection?: boolean
  onRedoSelection?: () => void

  // Offline mode
  sceneReady: boolean
  backgroundLoadingComplete: boolean
  labelsLoaded: boolean
  isOffline?: boolean
  onOfflineClick?: () => void

  // Database status
  dataSourceIndicator: 'postgres' | 'json' | 'offline' | 'error' | ''

  // Disclaimer
  onDisclaimerClick?: () => void

  // FPS display props
  gpuName: string | null
  lowFps: boolean
  lowFpsReady: boolean

  // Connectors status
  connectorsStatus?: StatusSummary
  onConnectorsClick?: () => void
}

export const OptionsPanel = forwardRef<HTMLDivElement, OptionsPanelProps>(({
  showTooltips,
  onToggleTooltips,
  showCoordinates,
  onToggleCoordinates,
  showScale,
  onToggleScale,
  hudScale,
  hudScalePreview,
  onHudScaleChange,
  onHudScalePreviewChange,
  dotSize,
  onDotSizeChange,
  onHideHud,
  onScreenshot,
  canUndoSelection,
  onUndoSelection,
  canRedoSelection,
  onRedoSelection,
  sceneReady,
  backgroundLoadingComplete,
  labelsLoaded,
  isOffline,
  onOfflineClick,
  dataSourceIndicator,
  onDisclaimerClick,
  gpuName,
  lowFps,
  lowFpsReady,
  connectorsStatus,
  onConnectorsClick
}, fpsRef) => {
  // Determine LED class for connectors
  const getConnectorsLedClass = () => {
    if (!connectorsStatus || connectorsStatus.total === 0) return 'unknown'
    if (connectorsStatus.error === connectorsStatus.total) return 'error'
    if (connectorsStatus.ok === connectorsStatus.total) return 'connected'
    if (connectorsStatus.error > 0 || connectorsStatus.warning > 0) return 'warning'
    if (connectorsStatus.unknown === connectorsStatus.total) return 'unknown'
    return 'connected'
  }
  return (
    <div className="info-panel-top-right">
      <FpsDisplay
        ref={fpsRef as React.RefObject<HTMLDivElement>}
        gpuName={gpuName}
        lowFps={lowFps}
        lowFpsReady={lowFpsReady}
      />
      <div className="options-section">
        <label className="option-toggle">
          <input
            type="checkbox"
            checked={showTooltips}
            onChange={onToggleTooltips}
          />
          <span>Tooltips</span>
        </label>
        <label className="option-toggle">
          <input
            type="checkbox"
            checked={showCoordinates}
            onChange={onToggleCoordinates}
          />
          <span>Coordinates</span>
        </label>
        <label className="option-toggle">
          <input
            type="checkbox"
            checked={showScale}
            onChange={onToggleScale}
          />
          <span>Scale</span>
        </label>

        {/* Settings Divider */}
        <div className="settings-divider" />

        {/* HUD Scale Slider */}
        <div className="setting-row">
          <span className="setting-label">HUD Scale</span>
          <input
            type="range"
            className="setting-slider"
            min={50}
            max={130}
            value={(hudScalePreview ?? hudScale) * 100}
            onChange={(e) => onHudScalePreviewChange(Number(e.target.value) / 100)}
            onMouseUp={(e) => {
              onHudScaleChange(Number((e.target as HTMLInputElement).value) / 100)
              onHudScalePreviewChange(null)
            }}
            onTouchEnd={(e) => {
              onHudScaleChange(Number((e.target as HTMLInputElement).value) / 100)
              onHudScalePreviewChange(null)
            }}
            onDoubleClick={() => {
              onHudScaleChange(0.9)
              onHudScalePreviewChange(null)
            }}
          />
        </div>

        {/* Dot Size Slider */}
        <div className="setting-row">
          <span className="setting-label">Dot Size</span>
          <input
            type="range"
            className="setting-slider"
            min={1}
            max={15}
            value={dotSize}
            onChange={(e) => onDotSizeChange(Number(e.target.value))}
            onDoubleClick={() => onDotSizeChange(6)}
          />
        </div>

        {/* Hide HUD / Screenshot / Undo / Redo Buttons */}
        <div className="hud-buttons">
          <button className="hud-btn" onClick={onHideHud} title="Hide HUD">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
              <line x1="1" y1="1" x2="23" y2="23" />
            </svg>
          </button>
          <button className="hud-btn" onClick={onScreenshot} title="Screenshot">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
              <circle cx="12" cy="13" r="4" />
            </svg>
          </button>
          <button
            className={`hud-btn ${!canUndoSelection ? 'disabled' : ''}`}
            onClick={canUndoSelection ? onUndoSelection : undefined}
            disabled={!canUndoSelection}
            title={canUndoSelection ? "Undo selection" : "Nothing to undo"}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
            </svg>
          </button>
          <button
            className={`hud-btn ${!canRedoSelection ? 'disabled' : ''}`}
            onClick={canRedoSelection ? onRedoSelection : undefined}
            disabled={!canRedoSelection}
            title={canRedoSelection ? "Redo selection" : "Nothing to redo"}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 12a9 9 0 1 1-9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
              <path d="M21 3v5h-5" />
            </svg>
          </button>
        </div>

        {/* Offline Mode Button - or Loading indicator during background loading */}
        {sceneReady && (!backgroundLoadingComplete || !labelsLoaded) ? (
          <div className="offline-mode-btn loading-state">
            <span className="offline-led loading" />
            <span>Loading...</span>
          </div>
        ) : onOfflineClick && (
          <button
            className="offline-mode-btn"
            onClick={onOfflineClick}
            title={isOffline ? 'Currently offline - manage cached data' : 'Download data for offline field use'}
          >
            <span className={`offline-led ${isOffline ? 'offline' : 'online'}`} />
            <span>{isOffline ? 'Offline Mode' : 'Online Mode'}</span>
          </button>
        )}

        {/* Database Connection Indicator */}
        {dataSourceIndicator && (
          <div
            className="database-status-indicator"
            title={
              dataSourceIndicator === 'postgres' ? 'Connected to PostgreSQL - edits will persist' :
              dataSourceIndicator === 'error' ? 'API not reachable - no data available' :
              dataSourceIndicator === 'json' ? 'Using static files - database unavailable' :
              'Using offline cache'
            }
          >
            <span className={`database-led ${
              dataSourceIndicator === 'postgres' ? 'connected' :
              dataSourceIndicator === 'error' ? 'error' :
              'disconnected'
            }`} />
            <span>{
              dataSourceIndicator === 'postgres' ? 'Database' :
              dataSourceIndicator === 'error' ? 'Offline' :
              'Static'
            }</span>
          </div>
        )}

        {/* Connectors Status Indicator */}
        {connectorsStatus && onConnectorsClick && (
          <div
            className="connectors-status-indicator"
            onClick={onConnectorsClick}
            title={`Connectors: ${connectorsStatus.ok}/${connectorsStatus.total} online. Click for details.`}
          >
            <span className={`connectors-led ${getConnectorsLedClass()}`} />
            <span>Connectors</span>
          </div>
        )}

        {/* Disclaimer Link */}
        {onDisclaimerClick && (
          <button
            className="disclaimer-settings-link"
            onClick={onDisclaimerClick}
          >
            Disclaimer & Legal
          </button>
        )}
      </div>
    </div>
  )
})

OptionsPanel.displayName = 'OptionsPanel'
